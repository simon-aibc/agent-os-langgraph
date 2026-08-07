# vault_qa

Skill ví dụ cho việc query kiến thức từ Second Brain sử dụng MemoryConnector.

## Usage

```bash
agent-os "hỏi vault: <câu hỏi của bạn>"
```

Skill sẽ tự động chọn connector tương ứng (MarkdownVaultConnector hoặc GbrainConnector) dựa trên cấu hình môi trường `AGENT_OS_MEMORY_CONNECTOR`.
