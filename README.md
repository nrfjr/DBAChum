# DBAChum

**DBAChum** is a self-hosted database administration and monitoring platform designed to provide a simple, centralized view of database infrastructure.

The project is currently under active development.

---

## Goals

DBAChum aims to provide a lightweight interface for database administrators to:

* Monitor database availability and health
* Manage database connection profiles
* View database and server information
* Track historical monitoring metrics
* Maintain server and infrastructure inventory
* Support multiple database engines
* Authenticate users locally or through LDAP
* Provide role-based access control
* Work as an installable Progressive Web App
* Run entirely on a local or self-hosted environment

---

## Supported Database Engines

Initial support:

* Oracle Database
* Microsoft SQL Server
* MySQL

---

## Tech Stack

### Frontend

* Vue 3
* TypeScript
* Vite
* Vue Router
* Pinia
* PrimeVue
* Progressive Web App support

### Backend

* Python
* FastAPI
* Pydantic
* PyMongo
* Database-specific Python connectors

### Application Database

* MongoDB


Just a small project for making database administration a little less painful.

## Production deployment

For Windows Server environments where Docker/WSL is unavailable, DBAChum supports a native Windows deployment. The production Vue build is served by FastAPI, MongoDB runs as its Windows service, and Task Scheduler keeps the application process running.

See [`docs/windows-deployment.md`](docs/windows-deployment.md), [`docs/windows-operations.md`](docs/windows-operations.md), and [`docs/security.md`](docs/security.md).
