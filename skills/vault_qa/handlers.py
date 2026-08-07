import os

from agent_os.connectors import GbrainConnector, MarkdownVaultConnector


# Simple global resolution for the memory connector for demonstration.
# In a full DI setup, this would be injected.
def _get_memory_connector():
    config = os.getenv("AGENT_OS_MEMORY_CONNECTOR", "markdown")
    if config == "gbrain":
        return GbrainConnector()
    else:
        # Default fallback
        vault_path = os.getenv("AGENT_OS_VAULT_PATH", "./sandbox")
        return MarkdownVaultConnector(vault_path)


def vault_qa(task: str, **kwargs) -> str:
    """
    Search the vault for the given query and return formatted results.
    """
    # Extract query after the trigger word if necessary, or just use task
    query = task
    prefix = "hỏi vault:"
    if task.lower().startswith(prefix):
        query = task[len(prefix):].strip()
        
    connector = _get_memory_connector()
    
    try:
        results = connector.search(query, limit=3)
    except Exception as e:
        return f"Lỗi khi tra cứu vault: {e}"
        
    if not results:
        return f"Không tìm thấy thông tin nào trong vault cho query: '{query}'"
        
    out = [f"Kết quả tra cứu cho '{query}':\n"]
    for i, res in enumerate(results, 1):
        ref = res.get("ref", "unknown")
        snippet = res.get("snippet", "")
        if not snippet:
            try:
                note = connector.read_note(ref)
                snippet = note.get("content", "")[:200]
            except Exception:
                pass
                
        out.append(f"{i}. [{ref}]\nTrích đoạn: {snippet}...\n")
        
    return "\n".join(out)
