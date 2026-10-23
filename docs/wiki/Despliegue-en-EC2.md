# Despliegue en EC2

Finty corre completo en **Docker Compose** sobre una instancia EC2 del **AWS Academy Learner Lab** (región `us-east-1`), con la IP elástica **3.95.100.48** (ADR-16). Solo Nginx publica un puerto (el 80); todo lo demás vive en la red interna de Compose.

```mermaid
flowchart TB
    U["Navegador<br/>(y servicio aliado, por asignar)"]

    subgraph AWS["AWS Academy · Learner Lab · región us-east-1"]
        EIP(["IP elástica 3.95.100.48"])
        subgraph SG["Grupo de seguridad finty-sg: entrada 22/tcp (SSH) y 80/tcp (HTTP)"]
            subgraph EC2["EC2 t3.medium · Ubuntu 24.04 LTS · 30 GB gp3 · Docker Engine + Compose v2"]
                subgraph NET["Red de Compose finty_default (bridge, DNS interno)"]
                    NGX["nginx · API Gateway<br/>único puerto publicado: 80<br/>auth_request · limit_req · estáticos con hash"]
                    DJ["django<br/>identity · frontend · /internal/"]
                    FIN["finance-service"]
                    REL["finance-outbox-relay"]
                    CAT["categorization-service"]
                    ANA["analytics-service"]
                    ANW["analytics-worker<br/>consume el stream"]
                    ACW["analytics-celery<br/>+ analytics-celery-beat"]
                    REC["recommendation-service"]
                    SUB["subscription-service"]
                    SCW["subscription-worker<br/>+ subscription-beat"]
                    RDS[("redis 7.4 · AOF<br/>base 0: stream finty.finance.events,<br/>cachés finty:entitlements:* y finty:fx:*<br/>base 1: broker de Celery<br/>(colas analytics y subscription)")]
                    PG[("postgres 18<br/>finty_identity · finty_finance<br/>finty_analytics · finty_recommendation<br/>finty_subscription")]
                    ONE["Pasos de un solo uso:<br/>db-init, migrate, finance-migrate,<br/>analytics-migrate, recommendation-migrate,<br/>subscription-migrate"]
                end
            end
        end
    end
    TRM["API de la TRM<br/>datos.gov.co"]

    U -->|"HTTP :80"| EIP --> NGX
    NGX -->|"/ , /api/v1/auth, /api/v1/profile, auth_request"| DJ
    NGX -->|"accounts · transactions · categories"| FIN
    NGX -->|"analytics · public"| ANA
    NGX -->|"recommendations · investment-plans · exchange-rates"| REC
    NGX -->|subscriptions| SUB
    FIN -->|"POST /v1/suggestions/"| CAT
    FIN --> PG
    REL -->|"lee outbox_event"| PG
    REL -->|XADD| RDS
    RDS -->|XREADGROUP| ANW
    ANW --> PG
    ANA -->|"encola reportes"| RDS
    RDS --> ACW
    ACW --> PG
    ANA --> PG
    ANA -->|"/internal/entitlements"| SUB
    REC -->|"/internal/entitlements"| SUB
    REC -->|"HTTP + X-User-Id"| ANA
    REC --> PG
    REC -->|"TrmExchangeRateProvider"| TRM
    SUB -->|"encola la bienvenida"| RDS
    RDS --> SCW
    SCW -->|"/internal/users/id/contact/"| DJ
    SCW --> PG
    SUB --> PG
    DJ --> PG
    ONE --> PG
```

| La instancia | |
|---|---|
| Sistema | Ubuntu Server 24.04 LTS (usuario `ubuntu`) |
| Tipo | `t3.medium` (2 vCPU, 4 GB) |
| Disco | 30 GB `gp3` |
| Red | IP elástica `3.95.100.48` y grupo de seguridad `finty-sg` (entrada solo por 22 y 80) |
| Acceso | EC2 Instance Connect, desde la consola |

## 1. Encender el laboratorio

1. Entra al curso de AWS Academy, abre **Learner Lab** y pulsa **Start Lab**. Espera a que el indicador quede en verde.
2. Pulsa **AWS** para abrir la consola, y ve a EC2 → Instances.
3. Las sesiones del Learner Lab duran unas horas. Al cerrarse, la instancia se detiene, pero **la IP elástica se conserva**, y con ella la dirección de la entrega.
4. Para entrar a la máquina: selecciona la instancia → **Connect** → pestaña **EC2 Instance Connect**, usuario `ubuntu` → **Connect**. Se abre una terminal en el navegador, sin llaves locales. Por eso el grupo de seguridad deja abierto el 22.

## 2. Crear la instancia (una sola vez)

| Opción | Valor |
|---|---|
| AMI | Ubuntu Server 24.04 LTS |
| Tipo | `t3.medium`: 4 GB de memoria para 15 contenedores de larga vida más los pasos de migración |
| Disco | 30 GB `gp3` (imágenes y volúmenes de PostgreSQL y Redis) |
| Grupo de seguridad | `finty-sg`: entrada **solo** por el 22/TCP (EC2 Instance Connect, para administrar) y el 80/TCP (HTTP, el Gateway) |

Después, en **Elastic IPs**: *Allocate Elastic IP address* y luego *Associate* con la instancia. Así la dirección no cambia al detener y encender la instancia.

## 3. Preparar la máquina (una sola vez)

En la terminal de EC2 Instance Connect:

```bash
curl -fsSL https://get.docker.com | sh       # Docker Engine y el plugin de Compose
sudo usermod -aG docker ubuntu                # cierra la terminal y vuelve a conectar para que aplique
docker compose version
```

Ubuntu 24.04 ya trae `git` y `python3` (este último lo usa `tools/seed_demo.py`).

## 4. Código y configuración (una sola vez)

```bash
git clone https://github.com/tsepulvedf/Finty.git && cd Finty
cp .env.docker.example .env.docker
for s in finance analytics recommendation subscription; do
  cp services/$s-service/.env.docker.example services/$s-service/.env.docker
done
```

| Archivo | Qué editar |
|---|---|
| `.env.docker` | `SECRET_KEY` propia, `DEBUG=False`, `ALLOWED_HOSTS` con `3.95.100.48` y la misma contraseña en `DB_PASSWORD` y `POSTGRES_PASSWORD` |
| `services/*-service/.env.docker` | Solo `DATABASE_URL`, con esa misma contraseña escapada en formato URL, y `TIME_ZONE`. Ningún otro secreto (A-21) |

Los `.env.docker` no se versionan (`.gitignore`).

## 5. Arrancar o actualizar

```bash
git pull
docker compose up -d --build
```

Los pasos de un solo uso dejan las bases al día antes de que arranque cada servicio. Una migración fallida impide arrancar contra un esquema incompleto.

| Paso | Qué hace |
|---|---|
| `db-init` | Crea las bases que falten |
| `migrate` | Corre las migraciones de Django |
| `finance-migrate` | Corre `alembic upgrade head` y siembra el catálogo de categorías |
| `analytics-migrate`, `recommendation-migrate`, `subscription-migrate` | Corren las migraciones de su servicio |

## 6. Comprobar

```bash
docker compose ps                               # todos Up; los servicios Flask (healthy)
curl http://3.95.100.48/api/v1/health/          # {"status":"ok","version":"v1"}
curl -I http://3.95.100.48/internal/auth/verify/   # 404: lo interno no se ve desde fuera
```

**Desde fuera:**
- Abre `http://3.95.100.48/` en el navegador.
- Compara el nombre con hash de la hoja de estilos con el del stack local: si coinciden, la instancia sirve la misma versión (así se verificó A-24 el 2026-10-22).

## 7. Datos de demostración

```bash
python3 tools/seed_demo.py --base-url http://3.95.100.48
```

Crea o completa, por la API, un usuario Free y uno Premium con 6 meses de movimientos. Es idempotente: una segunda corrida no duplica nada. Las credenciales están en [`docs/SUSTENTACION.md`](https://github.com/tsepulvedf/Finty/blob/main/docs/SUSTENTACION.md).

## Operación

```bash
docker compose logs -f finance-service analytics-worker    # registros
docker compose restart nginx                                # tras cambiar deploy/nginx/
docker compose down                                         # detener; los datos quedan en los volúmenes
```

**No uses `docker compose down -v` en la instancia:** borra las bases y Redis.
