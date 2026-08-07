import sys
import tomllib
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from agent_os.skills import RegisteredSkill


class SkillPackageLoader:
    def __init__(self, registry):
        self.registry = registry

    def load_from_directories(self, directories: list[str]) -> None:
        """Load skill packages from a list of directories."""
        for root_dir in directories:
            path = Path(root_dir)
            if not path.is_dir():
                continue
                
            for entry in path.iterdir():
                if entry.is_dir():
                    self.load_package(entry)

    def load_package(self, package_dir: Path) -> None:
        """Load a single skill package from its directory."""
        manifest_path = package_dir / "manifest.toml"
        if not manifest_path.exists():
            return
            
        try:
            with open(manifest_path, "rb") as f:
                manifest = tomllib.load(f)
        except Exception as e:
            raise ValueError(f"Failed to parse manifest {manifest_path}: {e}") from e
            
        if "skill" not in manifest or "handlers" not in manifest["skill"]:
            return
            
        skill_metadata = manifest["skill"]
        handlers = skill_metadata.get("handlers", [])
        
        for handler_conf in handlers:
            entrypoint = handler_conf.get("entrypoint")
            if not entrypoint:
                continue
                
            if ":" not in entrypoint:
                raise ValueError(f"Invalid entrypoint format '{entrypoint}' in {manifest_path}. Expected 'module:function'.")
                
            module_name, func_name = entrypoint.split(":", 1)
            module_path = package_dir / f"{module_name}.py"
            
            if not module_path.exists():
                raise ValueError(f"Module {module_path} not found for entrypoint {entrypoint}")
                
            spec = spec_from_file_location(module_name, module_path)
            if not spec or not spec.loader:
                raise ValueError(f"Failed to create spec for {module_path}")
                
            module = module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            if not hasattr(module, func_name):
                raise ValueError(f"Function {func_name} not found in {module_path}")
                
            func = getattr(module, func_name)
            
            matches = handler_conf.get("match", [])
            if not matches:
                continue
                
            name = matches[0]
            aliases = matches[1:]
            
            skill = RegisteredSkill(
                name=name,
                aliases=aliases,
                handler=func
            )
            self.registry.register(skill)
