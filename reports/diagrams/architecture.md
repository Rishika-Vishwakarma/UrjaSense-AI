# UrjaSense AI - architecture and ER diagram

## System architecture (local run and AWS target)
```mermaid
flowchart LR
  subgraph Browser
    U[Resident dashboard] --- L[Lineman dashboard] --- A[Admin dashboard]
  end
  Browser -->|HTTPS + JWT| GW[Amazon API Gateway*]
  GW --> API[Flask REST API on AWS Lambda* / local Flask]
  API --> SVC[Services: duplicate detection, workflow, notifications, analytics]
  SVC --> DB[(MySQL - Amazon RDS*)]
  SVC --> ML[ai_ml: restoration model, pattern analysis, categoriser]
  SVC -.optional.-> SNS[Amazon SNS*]
  API -.logs/alarms.-> CW[Amazon CloudWatch*]
  Browser -.static files.-> S3[Amazon S3 + CloudFront*]
```
\* AWS parts are configuration only (`aws/`); they are not deployed from this repository.

## Duplicate detection (score = proximity 0.5 + time 0.3 + issue 0.2, link when >= 0.55)
```mermaid
flowchart TD
  R[New report] --> O[Open incidents in same area]
  O --> S{Best score >= threshold?}
  S -- yes --> LINK[Link report to incident, recount distinct residents, refresh priority + estimate]
  S -- no --> NEW[Create new incident + REPORTED update]
  LINK --> N[Notify reporter]
  NEW --> N
```

## Entity relationships
```mermaid
erDiagram
  AREAS ||--o{ USERS : "home area"
  AREAS ||--o{ OUTAGE_INCIDENTS : has
  USERS ||--o| LINEMEN : "employee profile"
  USERS ||--o{ OUTAGE_REPORTS : files
  OUTAGE_INCIDENTS ||--|{ OUTAGE_REPORTS : groups
  OUTAGE_INCIDENTS ||--o{ INCIDENT_UPDATES : history
  OUTAGE_INCIDENTS ||--o{ ASSIGNMENTS : "assigned via"
  LINEMEN ||--o{ ASSIGNMENTS : works
  USERS ||--o{ NOTIFICATIONS : receives
  OUTAGE_INCIDENTS ||--o{ RATINGS : rated
  USERS ||--o{ RATINGS : gives
  USERS ||--o{ AUDIT_LOGS : performs
  AREAS ||--o{ HISTORICAL_OUTAGES : "analytics data (sample)"
```
