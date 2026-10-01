# AutoResolve Architecture

## Workflow

```mermaid
flowchart TD
 A[Tester] --> B[Workflow Manager]
 B --> C[Repository Retriever]
 C --> D[Root Cause Analyzer]
 D --> E[Patch Planner/Fixer]
 E --> F[Isolated Execution]
 F --> G{Validation}
 G -- fail --> E
 G -- pass --> H[Developer Review]
 H -- feedback --> E
 H -- approve --> I[Git Branch/PR]
 I --> J[Merge]
 J --> K[Tester Notification]
```

## Security boundary

LLM output is treated as untrusted. Patch application, test execution, Git operations and merge are controlled by application code. Production execution should use Docker with network restrictions and resource limits.
