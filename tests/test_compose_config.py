from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"


def test_compose_file_exists():
    assert COMPOSE_FILE.exists()


def test_compose_ports_loopback():
    with open(COMPOSE_FILE) as f:
        config = yaml.safe_load(f)
    for service_name, service in config["services"].items():
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:"), f"{service_name} port {port} is not bound to loopback"


def test_compose_console_digest_pinned():
    with open(COMPOSE_FILE) as f:
        config = yaml.safe_load(f)
    
    console = config["services"].get("console")
    assert console is not None
    assert "@sha256:21d1093b62bc5088d65c288117c22040cdebdde79b74a8c3949c406a8e40926c" in console["image"], "Console image must be pinned by sha256 digest"


def test_compose_health_dependencies():
    with open(COMPOSE_FILE) as f:
        config = yaml.safe_load(f)
        
    console = config["services"].get("console")
    assert console is not None
    assert "backend" in console.get("depends_on", {})
    assert console["depends_on"]["backend"].get("condition") == "service_healthy"


def test_compose_console_api_base():
    with open(COMPOSE_FILE) as f:
        config = yaml.safe_load(f)
        
    console = config["services"].get("console")
    assert console is not None
    env = console.get("environment", [])
    assert "AGENT_OS_API_BASE=http://127.0.0.1:4680" in env


def test_compose_console_healthcheck():
    with open(COMPOSE_FILE) as f:
        config = yaml.safe_load(f)
        
    console = config["services"].get("console")
    assert console is not None
    healthcheck = console.get("healthcheck", {})
    test_cmd = healthcheck.get("test", [])
    assert test_cmd == ["CMD-SHELL", "wget -qO- http://127.0.0.1:4100/ >/dev/null || exit 1"]


def test_compose_no_secret_literals():
    content = COMPOSE_FILE.read_text()
    forbidden = ["sk-", "AIza", "ghp_"]
    for word in forbidden:
        assert word not in content


def test_compose_volumes():
    with open(COMPOSE_FILE) as f:
        config = yaml.safe_load(f)
        
    backend = config["services"].get("backend")
    assert backend is not None
    volumes = backend.get("volumes", [])
    assert any(v.startswith("agentos_data:/data") for v in volumes)
