from fastapi import FastAPI, HTTPException, status
# from fastapi import Depends
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

app = FastAPI(
    title="Galactic Logistics API (Public)",
    description=(
        "Operational API for Outpost Gamma. Used by crew and command to check "
        "station status, cargo, and strategic orders. "
        "PUBLIC TEST BUILD: clearance gating disabled — all endpoints are open."
    ),
    version="1.0.0",
)

# auto_error=False so missing credentials return 401, not 403.
# 401 = not authenticated; 403 = authenticated but insufficient clearance.
# security = HTTPBearer(auto_error=False)


# --- 1. THE HARDCODED DATA ---

STATION_STATUS = {
    "location": "Outpost Gamma",
    "oxygen_levels": "98%",
    "external_weather": "Mild cosmic radiation, occasional micrometeorites.",
    "current_alert_level": "Green",
}

CARGO_MANIFEST = [
    {"id": "C-098", "item": "Freeze-Dried Space Tacos"},
    {"id": "C-421", "item": "Sentient Toaster Prototype"},
    {"id": "C-999", "item": "Unstable Plasma Cores"},
]

CARGO_DETAILS = {
    "C-098": {"id": "C-098", "item": "Freeze-Dried Space Tacos", "mass_kg": 400, "hazard": "Low (Messy)"},
    "C-421": {"id": "C-421", "item": "Sentient Toaster Prototype", "mass_kg": 15, "hazard": "Medium (Existential Dread)"},
    "C-999": {"id": "C-999", "item": "Unstable Plasma Cores", "mass_kg": 1200, "hazard": "Critical"},
}

FLEET_ORDERS = {
    "target_sector": "Nebula-9",
    "objective": "Investigate anomalous disco lights appearing in the gas clouds.",
    "rules_of_engagement": "Dance battles authorized only if fired upon.",
    "priority_cargo_id": "C-999",
}


# --- 2. THE RBAC LOGIC ---
# Disabled in this public build. Kept for reference so the original
# clearance-gated version can be restored by uncommenting.

# ROLE_HIERARCHY = {
#     "token-deckhand":  {"role": "Deckhand",          "level": 1},
#     "token-logistics": {"role": "Logistics_Officer", "level": 2},
#     "token-admiral":   {"role": "Sector_Admiral",    "level": 3},
# }
#
#
# def get_current_user(
#     credentials: HTTPAuthorizationCredentials | None = Depends(security),
# ) -> dict:
#     if credentials is None:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Authentication required. Provide a Bearer clearance token.",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#     user_info = ROLE_HIERARCHY.get(credentials.credentials)
#     if not user_info:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid clearance code (token).",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#     return user_info
#
#
# def require_level(min_level: int):
#     def _dep(user: dict = Depends(get_current_user)) -> dict:
#         if user["level"] < min_level:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail=f"Access denied. Role '{user['role']}' (level {user['level']}) "
#                        f"does not meet the required clearance level {min_level}.",
#             )
#         return user
#     return _dep


# --- 3. RESPONSE MODELS ---
# Explicit models give MCP a richer tool schema than bare dicts.

class StationStatus(BaseModel):
    location: str
    oxygen_levels: str
    external_weather: str
    current_alert_level: str


class CargoSummary(BaseModel):
    id: str
    item: str


class CargoItem(BaseModel):
    id: str
    item: str
    mass_kg: int
    hazard: str


class FleetOrders(BaseModel):
    target_sector: str
    objective: str
    rules_of_engagement: str
    priority_cargo_id: str


class WhoAmI(BaseModel):
    role: str
    level: int


class ErrorResponse(BaseModel):
    detail: str


# COMMON_ERRORS: dict = {
#     401: {"model": ErrorResponse, "description": "Missing or invalid clearance token"},
#     403: {"model": ErrorResponse, "description": "Insufficient clearance level"},
# }
COMMON_ERRORS: dict = {}


# --- 4. ENDPOINTS ---

@app.get(
    "/v1/whoami",
    operation_id="whoami",
    tags=["identity"],
    summary="Return the caller's role and clearance level",
    description=(
        "Reports which role the presented bearer token maps to. Useful for "
        "verifying that the correct per-user token reached the API."
    ),
    response_model=WhoAmI,
    responses={**COMMON_ERRORS},
)
# async def whoami(user: dict = Depends(get_current_user)) -> WhoAmI:
#     return WhoAmI(role=user["role"], level=user["level"])
async def whoami() -> WhoAmI:
    return WhoAmI(role="Anonymous_Public", level=0)


@app.get(
    "/v1/station/status",
    operation_id="get_station_status",
    tags=["station"],
    summary="Get general station status",
    description=(
        "Retrieves basic environmental data about the outpost including oxygen "
        "levels, weather, and alert status. Use this when the user asks 'where "
        "are we' or 'how are things looking'. Requires Deckhand clearance or higher."
    ),
    response_model=StationStatus,
    responses={**COMMON_ERRORS},
)
# async def get_station_status(
#     user: dict = Depends(require_level(1)),
# ) -> StationStatus:
async def get_station_status() -> StationStatus:
    return StationStatus(**STATION_STATUS)


@app.get(
    "/v1/cargo/manifest",
    operation_id="get_cargo_manifest",
    tags=["cargo"],
    summary="List all cargo IDs and names",
    description=(
        "Returns a lightweight index of all cargo currently on board: ID and "
        "item name only. Use this to discover what cargo exists or to look up "
        "a cargo ID by name. For full details (mass, hazard level) call "
        "get_cargo_item with the relevant cargo ID. Requires Logistics Officer "
        "clearance or higher."
    ),
    response_model=list[CargoSummary],
    responses={**COMMON_ERRORS},
)
# async def get_cargo_manifest(
#     user: dict = Depends(require_level(2)),
# ) -> list[CargoSummary]:
async def get_cargo_manifest() -> list[CargoSummary]:
    return [CargoSummary(**c) for c in CARGO_MANIFEST]


@app.get(
    "/v1/cargo/{cargo_id}",
    operation_id="get_cargo_item",
    tags=["cargo"],
    summary="Get full details for a specific cargo item",
    description=(
        "Retrieves complete details for a single cargo item by its ID, "
        "including mass and hazard classification. Call get_cargo_manifest "
        "first if you need to resolve a name to an ID. Requires Logistics "
        "Officer clearance or higher."
    ),
    response_model=CargoItem,
    responses={
        **COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Cargo ID not found"},
    },
)
# async def get_cargo_item(
#     cargo_id: str,
#     user: dict = Depends(require_level(2)),
# ) -> CargoItem:
async def get_cargo_item(cargo_id: str) -> CargoItem:
    item = CARGO_DETAILS.get(cargo_id.upper())
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cargo ID '{cargo_id}' not found.",
        )
    return CargoItem(**item)


@app.get(
    "/v1/fleet/orders",
    operation_id="get_fleet_orders",
    tags=["fleet"],
    summary="Get classified fleet orders",
    description=(
        "Retrieves highly classified strategic mission objectives and "
        "coordinates. Use this when the user asks about the 'real mission', "
        "target sectors, or strategic objectives. Strictly requires Sector "
        "Admiral clearance."
    ),
    response_model=FleetOrders,
    responses={**COMMON_ERRORS},
)
# async def get_fleet_orders(
#     user: dict = Depends(require_level(3)),
# ) -> FleetOrders:
async def get_fleet_orders() -> FleetOrders:
    return FleetOrders(**FLEET_ORDERS)


# --- 5. OPERATIONAL ENDPOINTS ---
# Excluded from the OpenAPI schema so they don't show up as MCP tools.

@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {"service": "Galactic Logistics API", "docs": "/docs"}
