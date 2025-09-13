# TODO

- [ ] Design in-memory pub/sub topic manager for action-terminal
- [ ] Add session-to-topic subscription management APIs to action-terminal
- [ ] Stream terminal output and session state to topics in action-terminal
- [ ] Expose state query API for sessions in action-terminal
- [ ] Add unit and integration tests for topics and state
- [ ] Scaffold action-webapp (FastAPI, SQLAlchemy, Alembic, Postgres)
- [ ] Implement sessions CRUD and queue subscription in action-webapp
- [ ] Persist incoming messages to Postgres in action-webapp
- [ ] Add API to fetch session data and incremental updates
- [ ] Add unit and integration tests for action-webapp
- [ ] Scaffold frontend (Vite, React, TypeScript)
- [ ] Implement sessions list and session detail views
- [ ] Implement process view with output, queues, and controls
- [ ] Add polling for updates and data fetching
- [ ] Add Jest unit tests and Playwright E2E tests
