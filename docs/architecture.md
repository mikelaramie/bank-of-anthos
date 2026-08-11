# Bank of Anthos — Architecture

## Service Diagram

```mermaid
flowchart TD
    Browser([Browser])
    LG([Load Generator])

    subgraph Frontend
        FE[frontend\nPython/Flask]
    end

    subgraph Accounts Domain
        US[userservice\nPython]
        CO[contacts\nPython]
        ADB[(accounts-db\nPostgreSQL)]
    end

    subgraph Ledger Domain
        LW[ledger-writer\nJava/Spring]
        BR[balance-reader\nJava/Spring]
        TH[transaction-history\nJava/Spring]
        LDB[(ledger-db\nPostgreSQL)]
    end

    Browser -->|HTTP| FE
    LG -->|HTTP| FE

    FE -->|login / signup| US
    FE -->|contacts list| CO
    FE -->|submit transaction| LW
    FE -->|get balance| BR
    FE -->|get history| TH

    US -->|read/write| ADB
    CO -->|read/write| ADB

    LW -->|write transaction| LDB
    BR -->|poll / read| LDB
    TH -->|poll / read| LDB
```

## Authentication Flow

```mermaid
sequenceDiagram
    participant Browser
    participant frontend
    participant userservice
    participant backend as ledger-writer / balance-reader / transaction-history

    Browser->>frontend: POST /login (username, password)
    frontend->>userservice: POST /login
    userservice-->>frontend: JWT (signed with RSA private key)
    frontend-->>Browser: Set session cookie (JWT)

    Browser->>frontend: GET /home
    frontend->>backend: Request + JWT (Bearer)
    backend->>backend: Verify JWT (RSA public key)
    backend-->>frontend: Response data
    frontend-->>Browser: Rendered page
```

## Service Summary

| Service | Language | Port | Role |
|---|---|---|---|
| frontend | Python/Flask | 8080 | Web UI, BFF — fans out to all backend services |
| userservice | Python | 8080 | User registration, login, JWT signing |
| contacts | Python | 8080 | Manage linked external accounts per user |
| ledger-writer | Java/Spring | 8080 | Validate and write new transactions |
| balance-reader | Java/Spring | 8080 | Cached read of current account balances |
| transaction-history | Java/Spring | 8080 | Cached read of past transactions |
| accounts-db | PostgreSQL | 5432 | Stores user credentials and contact lists |
| ledger-db | PostgreSQL | 5432 | Immutable transaction ledger |
| loadgenerator | Python/Locust | — | Simulates user traffic for demos |

## Key Design Notes

- **Read/write separation**: `ledger-writer` handles all writes; `balance-reader` and `transaction-history` are independent read services that poll `ledger-db`.
- **Stateless auth**: `userservice` signs JWTs with an RSA private key. All other services verify them using the public key mounted from a shared Kubernetes Secret — no shared session store.
- **BFF pattern**: The `frontend` is the only service that calls other services. Backend services are all leaf nodes with no inter-service calls.
- **Kustomize overlays**: Each service has `base` manifests plus `development`, `staging`, `production`, and `production-fwi` overlays.
