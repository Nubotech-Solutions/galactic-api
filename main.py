import copy
import os
from pathlib import Path as FilePath
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Path, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────
# 1.  RBAC
# ──────────────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)

ROLE_HIERARCHY: dict[str, dict] = {
    "token-deckhand":  {"role": "Deckhand",          "level": 1},
    "token-logistics": {"role": "Logistics_Officer", "level": 2},
    "token-admiral":   {"role": "Sector_Admiral",    "level": 3},
}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a Bearer clearance token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_info = ROLE_HIERARCHY.get(credentials.credentials)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid clearance token. Access denied.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_info


def require_level(min_level: int):
    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user["level"] < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Clearance denied. Your role '{user['role']}' is level "
                    f"{user['level']}; this endpoint requires level {min_level} or above."
                ),
            )
        return user
    return _dep


# ──────────────────────────────────────────────────────────────
# 2.  SEED DATA
# ──────────────────────────────────────────────────────────────
#
# These _SEED_* constants are the pristine, never-mutated source of truth.
# The live, mutable in-memory store is built from deep copies of them in
# reset_state() below, so write endpoints can mutate state freely and the
# hidden reset endpoint can restore everything to this baseline.

_SEED_STATION_STATUS = {
    "location": "Outpost Gamma",
    "oxygen_levels": "98%",
    "external_weather": "Mild cosmic radiation, occasional micrometeorites.",
    "current_alert_level": "Green",
}

_SEED_STATION_SYSTEMS = [
    {
        "system_id": "SYS-01", "name": "Life Support",
        "status": "Online", "health_pct": 98, "notes": None,
    },
    {
        "system_id": "SYS-02", "name": "Navigation",
        "status": "Online", "health_pct": 100, "notes": None,
    },
    {
        "system_id": "SYS-03", "name": "Weapons Array",
        "status": "Standby", "health_pct": 75,
        "notes": "On standby per Green alert protocol. Ready to activate within 90 seconds.",
    },
    {
        "system_id": "SYS-04", "name": "Communications",
        "status": "Degraded", "health_pct": 60,
        "notes": "Array damaged during recent ion storm. Repair crew dispatched; ETA 6 hours.",
    },
    {
        "system_id": "SYS-05", "name": "Cargo Bay",
        "status": "Online", "health_pct": 100, "notes": None,
    },
    {
        "system_id": "SYS-06", "name": "Engine Core",
        "status": "Maintenance", "health_pct": 40,
        "notes": "Scheduled upgrade underway. Engineer Tanaka assigned. ETA 48 hours.",
    },
    {
        "system_id": "SYS-07", "name": "Shield Grid",
        "status": "Online", "health_pct": 89, "notes": None,
    },
]

_SEED_CREW: dict[str, dict] = {
    "CR-001": {
        "crew_id": "CR-001",
        "name": "Zara Khan",
        "role": "Captain",
        "clearance_level": 3,
        "duty_status": "On Duty",
        "certifications": ["Hazmat Handling", "Combat Operations", "Advanced Navigation", "Command Protocols"],
        "notes": "Commanding officer of Outpost Gamma. Authorized signatory for all Level 3 orders.",
    },
    "CR-002": {
        "crew_id": "CR-002",
        "name": "Marcus Webb",
        "role": "Logistics Officer",
        "clearance_level": 2,
        "duty_status": "On Duty",
        "certifications": ["Cargo Handling", "Trade Liaison", "Inventory Management"],
        "notes": "Specialist in interplanetary trade negotiations and cargo routing.",
    },
    "CR-003": {
        "crew_id": "CR-003",
        "name": "Yuki Tanaka",
        "role": "Engineer",
        "clearance_level": 1,
        "duty_status": "On Duty",
        "certifications": ["Hull Repair", "Engine Systems", "Atmospheric Maintenance"],
        "notes": "Currently assigned to Engine Core upgrade (SYS-06). Expected back on general rotation in 48 hours.",
    },
    "CR-004": {
        "crew_id": "CR-004",
        "name": "Rex Oduya",
        "role": "Security Officer",
        "clearance_level": 2,
        "duty_status": "Off Duty",
        "certifications": ["Weapons Systems", "Boarding Operations", "Threat Assessment"],
        "notes": "Off rotation. Returns to active duty in 12 hours.",
    },
    "CR-005": {
        "crew_id": "CR-005",
        "name": "Lena Moreau",
        "role": "Chief Medic",
        "clearance_level": 1,
        "duty_status": "On Duty",
        "certifications": ["Emergency Medicine", "Bio-Hazard Response", "Trauma Surgery"],
        "notes": "Oversees all medical operations and bio-hazard cargo handling clearances.",
    },
    "CR-006": {
        "crew_id": "CR-006",
        "name": "Dax Vorne",
        "role": "Pilot",
        "clearance_level": 2,
        "duty_status": "On Duty",
        "certifications": ["Shuttle Operations", "Convoy Escort", "Combat Maneuvers", "Deep Space Navigation"],
        "notes": "Primary pilot for all convoy and mission deployments.",
    },
}

_SEED_CARGO_MANIFEST = [
    {"id": "C-098", "item": "Freeze-Dried Space Tacos"},
    {"id": "C-112", "item": "Medical Supplies Batch-7"},
    {"id": "C-234", "item": "Diplomatic Data Crystals"},
    {"id": "C-333", "item": "Hydroponic Seeds"},
    {"id": "C-421", "item": "Sentient Toaster Prototype"},
    {"id": "C-567", "item": "Nanite Repair Swarm"},
    {"id": "C-777", "item": "Cloaking Device Prototype"},
    {"id": "C-999", "item": "Unstable Plasma Cores"},
]

_SEED_CARGO_DETAILS: dict[str, dict] = {
    "C-098": {
        "id": "C-098", "item": "Freeze-Dried Space Tacos", "mass_kg": 400,
        "hazard": "Low (Messy)", "category": "Food Supplies",
        "inspection_status": "Inspected",
        "origin": "Outpost Gamma", "destination": "Waystation Delta",
    },
    "C-112": {
        "id": "C-112", "item": "Medical Supplies Batch-7", "mass_kg": 200,
        "hazard": "Low (Handle with Care)", "category": "Medical",
        "inspection_status": "Inspected",
        "origin": "Earth Medical Authority", "destination": "Waystation Delta",
    },
    "C-234": {
        "id": "C-234", "item": "Diplomatic Data Crystals", "mass_kg": 2,
        "hazard": "Medium (Classified)", "category": "Intelligence",
        "inspection_status": "Pending Inspection",
        "origin": "Nebula-7 Embassy", "destination": "Outpost Gamma",
    },
    "C-333": {
        "id": "C-333", "item": "Hydroponic Seeds", "mass_kg": 150,
        "hazard": "Low (Organic)", "category": "Agriculture",
        "inspection_status": "Inspected",
        "origin": "Earth Agricultural Bureau", "destination": "Colony Station Zeta",
    },
    "C-421": {
        "id": "C-421", "item": "Sentient Toaster Prototype", "mass_kg": 15,
        "hazard": "Medium (Existential Dread)", "category": "Experimental",
        "inspection_status": "Pending Inspection",
        "origin": "Outpost Gamma R&D Lab", "destination": "Research Lab Kepler",
    },
    "C-567": {
        "id": "C-567", "item": "Nanite Repair Swarm", "mass_kg": 8,
        "hazard": "High (Containment Required)", "category": "Experimental",
        "inspection_status": "Flagged",
        "origin": "Kepler Research Station", "destination": "Outpost Gamma",
    },
    "C-777": {
        "id": "C-777", "item": "Cloaking Device Prototype", "mass_kg": 45,
        "hazard": "Critical (Classified)", "category": "Military Technology",
        "inspection_status": "Restricted",
        "origin": "High Command Armory", "destination": "Nebula-9",
    },
    "C-999": {
        "id": "C-999", "item": "Unstable Plasma Cores", "mass_kg": 1200,
        "hazard": "Critical", "category": "Energy",
        "inspection_status": "Restricted",
        "origin": "Nebula-9 Mining Collective", "destination": "Nebula-9",
    },
}

_SEED_SHIPMENTS: dict[str, dict] = {
    "SH-001": {
        "shipment_id": "SH-001", "convoy_name": "Convoy Orion",
        "status": "In Transit", "origin": "Outpost Gamma", "destination": "Waystation Delta",
        "eta": "3 days", "cargo_ids": ["C-098", "C-112"],
        "delay_reason": None,
        "notes": "Routine supply convoy proceeding on schedule.",
    },
    "SH-002": {
        "shipment_id": "SH-002", "convoy_name": "Convoy Hydra",
        "status": "Delayed", "origin": "Outpost Gamma", "destination": "Research Lab Kepler",
        "eta": "Unknown — awaiting repair", "cargo_ids": ["C-421"],
        "delay_reason": "Engine malfunction on lead vessel. Engineering team dispatched.",
        "notes": "Convoy stationary at checkpoint Hydra-4 for 18 hours.",
    },
    "SH-003": {
        "shipment_id": "SH-003", "convoy_name": "Convoy Perseus",
        "status": "Arrived", "origin": "Nebula-7", "destination": "Outpost Gamma",
        "eta": "Completed", "cargo_ids": ["C-234"],
        "delay_reason": None,
        "notes": "Diplomatic cargo delivered. Awaiting inspection clearance from Chief Medic.",
    },
    "SH-004": {
        "shipment_id": "SH-004", "convoy_name": "Convoy Lyra",
        "status": "In Transit", "origin": "Outpost Gamma", "destination": "Nebula-9",
        "eta": "6 days", "cargo_ids": ["C-777", "C-999"],
        "delay_reason": None,
        "notes": "Mission-critical cargo. Escort authorized. Report status to Admiral clearance only.",
    },
    "SH-005": {
        "shipment_id": "SH-005", "convoy_name": "Convoy Atlas",
        "status": "Loading", "origin": "Outpost Gamma", "destination": "Colony Station Zeta",
        "eta": "Departs in 24 hours", "cargo_ids": ["C-333"],
        "delay_reason": None,
        "notes": "Agricultural supply run to outer colonies.",
    },
}

_SEED_TRADE_MANIFESTS: dict[str, dict] = {
    "TM-001": {
        "manifest_id": "TM-001", "counterparty": "Kepler Research Station",
        "status": "Active",
        "description": "Exchange of medical supplies and experimental equipment for advanced research data.",
        "value_credits": 8500, "cargo_ids": ["C-112", "C-421"],
        "notes": "Renewal negotiated by Logistics Officer Webb. Contract expires in 90 days.",
    },
    "TM-002": {
        "manifest_id": "TM-002", "counterparty": "Waystation Delta",
        "status": "Completed",
        "description": "Food rations and agricultural supplies in exchange for refined fuel cells.",
        "value_credits": 3200, "cargo_ids": ["C-098", "C-333"],
        "notes": "Fully settled. Next cycle negotiation scheduled in 45 days.",
    },
    "TM-003": {
        "manifest_id": "TM-003", "counterparty": "Nebula-9 Mining Collective",
        "status": "Pending",
        "description": "High-value energy resource delivery contract. Terms under High Command review.",
        "value_credits": 85000, "cargo_ids": ["C-999"],
        "notes": "Classified contract. Do not discuss with personnel below Admiral clearance.",
    },
    "TM-004": {
        "manifest_id": "TM-004", "counterparty": "Earth Diplomatic Corps",
        "status": "Active",
        "description": "Cultural and intelligence data exchange under the Nebula-7 Accord.",
        "value_credits": 12000, "cargo_ids": ["C-234"],
        "notes": "Handled directly by Captain Khan per diplomatic protocol.",
    },
}

_SEED_FLEET_ORDERS = {
    "target_sector": "Nebula-9",
    "objective": (
        "Investigate anomalous energy signatures detected along the Nebula-9 gas cloud perimeter. "
        "Identify source and assess threat level. Report findings directly to High Command."
    ),
    "secondary_objective": (
        "Establish contact with the Nebula-9 Mining Collective and secure the pending trade route "
        "for plasma core extraction (ref. TM-003)."
    ),
    "rules_of_engagement": (
        "Defensive posture only. Shields and evasive maneuvers authorized without prior approval. "
        "Escalate to Command before any offensive action."
    ),
    "priority_cargo_ids": ["C-999", "C-777"],
}

_SEED_MISSIONS: dict[str, dict] = {
    "MISSION-ALPHA": {
        "mission_id": "MISSION-ALPHA",
        "name": "Nebula-9 Reconnaissance",
        "status": "Active",
        "target_sector": "Nebula-9",
        "assigned_crew_ids": ["CR-001", "CR-006"],
        "objective": (
            "Scout the Nebula-9 perimeter for the anomalous energy source flagged by long-range sensors. "
            "Escort Convoy Lyra (SH-004) to the Nebula-9 Anchorage and ensure delivery of priority cargo."
        ),
        "notes": "Captain Khan leads. Departure aligned with Convoy Lyra schedule.",
    },
    "MISSION-BETA": {
        "mission_id": "MISSION-BETA",
        "name": "Waystation Delta Supply Run",
        "status": "Completed",
        "target_sector": "Waystation Delta",
        "assigned_crew_ids": ["CR-002", "CR-006"],
        "objective": "Deliver food and medical supplies to Waystation Delta and return with fuel cell shipment.",
        "notes": "Completed without incident. Trade manifest TM-002 settled in full.",
    },
    "MISSION-GAMMA": {
        "mission_id": "MISSION-GAMMA",
        "name": "Deep Space Anomaly Investigation",
        "status": "Active",
        "target_sector": "Unknown Sector 7",
        "assigned_crew_ids": ["CR-001", "CR-004"],
        "objective": (
            "Investigate an uncharted gravitational anomaly in Sector 7. "
            "Classify threat level and report findings to High Command. "
            "Authorized to use lethal force if anomaly poses immediate danger to the station."
        ),
        "notes": "Communication blackout expected for the operation duration. Last contact in 14 hours.",
    },
}

# Records flagged Admiral-only (level 3) in their own data. They are hidden from
# level-2 list responses and return 403 on their detail endpoints below level 3.
CLASSIFIED_SHIPMENT_IDS = {"SH-004"}
CLASSIFIED_MANIFEST_IDS = {"TM-003"}
CLASSIFIED_CARGO_IDS = {"C-777", "C-999"}


# ──────────────────────────────────────────────────────────────
# 2b.  LIVE IN-MEMORY STORE
# ──────────────────────────────────────────────────────────────
#
# The write endpoints mutate these module-level globals in place. reset_state()
# rebuilds them from deep copies of the _SEED_* baseline, so the (hidden) reset
# endpoint can discard all mutations. Summaries are derived on the fly in the
# list handlers, so writes are reflected without maintaining separate caches.

STATION_STATUS: dict
STATION_SYSTEMS: list[dict]
CREW: dict[str, dict]
CARGO_MANIFEST: list[dict]
CARGO_DETAILS: dict[str, dict]
SHIPMENTS: dict[str, dict]
TRADE_MANIFESTS: dict[str, dict]
FLEET_ORDERS: dict
MISSIONS: dict[str, dict]


def reset_state() -> None:
    """Restore the live in-memory store to the pristine _SEED_* baseline."""
    global STATION_STATUS, STATION_SYSTEMS, CREW, CARGO_MANIFEST, CARGO_DETAILS
    global SHIPMENTS, TRADE_MANIFESTS, FLEET_ORDERS, MISSIONS
    STATION_STATUS = copy.deepcopy(_SEED_STATION_STATUS)
    STATION_SYSTEMS = copy.deepcopy(_SEED_STATION_SYSTEMS)
    CREW = copy.deepcopy(_SEED_CREW)
    CARGO_MANIFEST = copy.deepcopy(_SEED_CARGO_MANIFEST)
    CARGO_DETAILS = copy.deepcopy(_SEED_CARGO_DETAILS)
    SHIPMENTS = copy.deepcopy(_SEED_SHIPMENTS)
    TRADE_MANIFESTS = copy.deepcopy(_SEED_TRADE_MANIFESTS)
    FLEET_ORDERS = copy.deepcopy(_SEED_FLEET_ORDERS)
    MISSIONS = copy.deepcopy(_SEED_MISSIONS)


# Initialize the live store at import time.
reset_state()


# ──────────────────────────────────────────────────────────────
# 3.  RESPONSE MODELS
# ──────────────────────────────────────────────────────────────

class WhoAmI(BaseModel):
    role: str = Field(
        description="Role name associated with the presented clearance token.",
        examples=["Logistics_Officer"],
    )
    level: int = Field(
        description="Numeric clearance level. 0 = unauthenticated, 1 = Deckhand, 2 = Logistics Officer, 3 = Sector Admiral.",
        examples=[2],
    )


class StationStatus(BaseModel):
    location: str = Field(description="Name of the station or outpost.", examples=["Outpost Gamma"])
    oxygen_levels: str = Field(description="Current oxygen concentration in breathable areas.", examples=["98%"])
    external_weather: str = Field(
        description="Current environmental conditions outside the hull.",
        examples=["Mild cosmic radiation, occasional micrometeorites."],
    )
    current_alert_level: str = Field(
        description="Operational alert level. Green = normal operations, Yellow = elevated caution, Red = emergency.",
        examples=["Green"],
    )


class StationSystem(BaseModel):
    system_id: str = Field(description="Unique system identifier.", examples=["SYS-04"])
    name: str = Field(description="Human-readable name of the station subsystem.", examples=["Communications"])
    status: str = Field(
        description="Current operational status. One of: Online, Standby, Degraded, Maintenance.",
        examples=["Degraded"],
    )
    health_pct: int = Field(
        description="Health percentage from 0 (failed) to 100 (optimal).",
        examples=[60],
        ge=0,
        le=100,
    )
    notes: str | None = Field(
        default=None,
        description="Engineering note explaining the current status, if any.",
        examples=["Array damaged during recent ion storm. Repair crew dispatched; ETA 6 hours."],
    )


class CrewSummary(BaseModel):
    crew_id: str = Field(description="Unique crew member identifier.", examples=["CR-002"])
    name: str = Field(description="Full name of the crew member.", examples=["Marcus Webb"])
    role: str = Field(description="Operational role aboard the station.", examples=["Logistics Officer"])
    duty_status: str = Field(
        description="Current duty status. One of: On Duty, Off Duty.",
        examples=["On Duty"],
    )


class CrewMember(BaseModel):
    crew_id: str = Field(description="Unique crew member identifier.", examples=["CR-002"])
    name: str = Field(description="Full name of the crew member.", examples=["Marcus Webb"])
    role: str = Field(description="Operational role aboard the station.", examples=["Logistics Officer"])
    clearance_level: int = Field(
        description="Personnel security clearance level (1 = Deckhand, 2 = Logistics Officer, 3 = Admiral).",
        examples=[2],
    )
    duty_status: str = Field(
        description="Current duty status. One of: On Duty, Off Duty.",
        examples=["On Duty"],
    )
    certifications: list[str] = Field(
        description="List of operational certifications held by this crew member.",
        examples=[["Cargo Handling", "Trade Liaison", "Inventory Management"]],
    )
    notes: str | None = Field(
        default=None,
        description="Additional personnel notes from the commanding officer.",
        examples=["Specialist in interplanetary trade negotiations."],
    )


class CargoSummary(BaseModel):
    id: str = Field(description="Unique cargo identifier in format C-NNN.", examples=["C-112"])
    item: str = Field(description="Brief name of the cargo item.", examples=["Medical Supplies Batch-7"])


class CargoItem(BaseModel):
    id: str = Field(description="Unique cargo identifier.", examples=["C-421"])
    item: str = Field(description="Full descriptive name of the cargo item.", examples=["Sentient Toaster Prototype"])
    mass_kg: int = Field(description="Total mass of this cargo lot in kilograms.", examples=[15])
    hazard: str = Field(
        description="Hazard classification and risk descriptor. Levels: Low, Medium, High, Critical.",
        examples=["Medium (Existential Dread)"],
    )
    category: str = Field(
        description="Operational category used for cargo routing and handling rules.",
        examples=["Experimental"],
    )
    inspection_status: str = Field(
        description=(
            "Current inspection status. One of: Inspected (cleared), Pending Inspection (awaiting review), "
            "Flagged (requires immediate review), Restricted (Admiral clearance only)."
        ),
        examples=["Pending Inspection"],
    )
    origin: str = Field(description="Station or sector where this cargo originated.", examples=["Outpost Gamma R&D Lab"])
    destination: str = Field(description="Intended destination station or sector.", examples=["Research Lab Kepler"])


class ShipmentSummary(BaseModel):
    shipment_id: str = Field(description="Unique shipment identifier.", examples=["SH-002"])
    convoy_name: str = Field(description="Operational name of the convoy.", examples=["Convoy Hydra"])
    status: str = Field(
        description="Current convoy status. One of: Loading, In Transit, Delayed, Arrived.",
        examples=["Delayed"],
    )
    origin: str = Field(description="Departure station or sector.", examples=["Outpost Gamma"])
    destination: str = Field(description="Destination station or sector.", examples=["Research Lab Kepler"])
    eta: str | None = Field(
        default=None,
        description="Estimated time of arrival or status note if arrival time is unavailable.",
        examples=["Unknown — awaiting repair"],
    )
    cargo_ids: list[str] = Field(
        description="List of cargo IDs currently aboard this convoy.",
        examples=[["C-421"]],
    )


class ShipmentDetail(BaseModel):
    shipment_id: str = Field(description="Unique shipment identifier.", examples=["SH-002"])
    convoy_name: str = Field(description="Operational name of the convoy.", examples=["Convoy Hydra"])
    status: str = Field(
        description="Current convoy status. One of: Loading, In Transit, Delayed, Arrived.",
        examples=["Delayed"],
    )
    origin: str = Field(description="Departure station or sector.", examples=["Outpost Gamma"])
    destination: str = Field(description="Destination station or sector.", examples=["Research Lab Kepler"])
    eta: str | None = Field(
        default=None,
        description="Estimated time of arrival, or a status note if ETA is unavailable.",
        examples=["Unknown — awaiting repair"],
    )
    cargo_ids: list[str] = Field(
        description="List of cargo IDs aboard this convoy.",
        examples=[["C-421"]],
    )
    delay_reason: str | None = Field(
        default=None,
        description="If status is Delayed, the reason for the delay. Null otherwise.",
        examples=["Engine malfunction on lead vessel. Engineering team dispatched."],
    )
    notes: str | None = Field(
        default=None,
        description="Additional operational notes from logistics command.",
        examples=["Convoy stationary at checkpoint Hydra-4 for 18 hours."],
    )


class TradeManifestSummary(BaseModel):
    manifest_id: str = Field(description="Unique trade manifest identifier.", examples=["TM-001"])
    counterparty: str = Field(
        description="The external faction or station that is the other party in this contract.",
        examples=["Kepler Research Station"],
    )
    status: str = Field(
        description="Contract status. One of: Active (ongoing), Completed (settled), Pending (under review).",
        examples=["Active"],
    )
    description: str = Field(
        description="Summary of goods and services being exchanged under this contract.",
        examples=["Exchange of medical supplies and experimental equipment for advanced research data."],
    )
    value_credits: int = Field(
        description="Total contract value in galactic standard credits.",
        examples=[8500],
    )


class TradeManifestDetail(BaseModel):
    manifest_id: str = Field(description="Unique trade manifest identifier.", examples=["TM-001"])
    counterparty: str = Field(
        description="The external faction or station that is the other party in this contract.",
        examples=["Kepler Research Station"],
    )
    status: str = Field(
        description="Contract status. One of: Active, Completed, Pending.",
        examples=["Active"],
    )
    description: str = Field(
        description="Summary of goods and services being exchanged.",
        examples=["Exchange of medical supplies and experimental equipment for advanced research data."],
    )
    value_credits: int = Field(
        description="Total contract value in galactic standard credits.",
        examples=[8500],
    )
    cargo_ids: list[str] = Field(
        description="Cargo IDs involved in this trade contract.",
        examples=[["C-112", "C-421"]],
    )
    notes: str | None = Field(
        default=None,
        description="Operational notes from the logistics officer managing this contract.",
        examples=["Renewal negotiated by Logistics Officer Webb. Contract expires in 90 days."],
    )


class FleetOrders(BaseModel):
    target_sector: str = Field(
        description="Primary operational sector for current fleet deployment.",
        examples=["Nebula-9"],
    )
    objective: str = Field(
        description="Primary mission objective as issued by High Command.",
        examples=["Investigate anomalous energy signatures detected along the Nebula-9 gas cloud perimeter."],
    )
    secondary_objective: str = Field(
        description="Secondary mission objective to be completed if primary is achieved.",
        examples=["Establish contact with the Nebula-9 Mining Collective and secure the trade route."],
    )
    rules_of_engagement: str = Field(
        description="Authorized engagement protocols currently in effect.",
        examples=["Defensive posture only. Escalate to Command before any offensive action."],
    )
    priority_cargo_ids: list[str] = Field(
        description="Cargo IDs designated mission-critical. Must be protected and delivered at all costs.",
        examples=[["C-999", "C-777"]],
    )


class MissionSummary(BaseModel):
    mission_id: str = Field(description="Unique mission identifier.", examples=["MISSION-ALPHA"])
    name: str = Field(description="Operational name of the mission.", examples=["Nebula-9 Reconnaissance"])
    status: str = Field(
        description="Mission status. One of: Active, Completed, Aborted.",
        examples=["Active"],
    )
    target_sector: str = Field(description="Primary sector or destination for this mission.", examples=["Nebula-9"])
    assigned_crew_ids: list[str] = Field(
        description="Crew member IDs assigned to this mission.",
        examples=[["CR-001", "CR-006"]],
    )


class MissionDetail(BaseModel):
    mission_id: str = Field(description="Unique mission identifier.", examples=["MISSION-ALPHA"])
    name: str = Field(description="Operational name of the mission.", examples=["Nebula-9 Reconnaissance"])
    status: str = Field(
        description="Mission status. One of: Active, Completed, Aborted.",
        examples=["Active"],
    )
    target_sector: str = Field(description="Primary sector or destination for this mission.", examples=["Nebula-9"])
    assigned_crew_ids: list[str] = Field(
        description="Crew member IDs assigned to this mission.",
        examples=[["CR-001", "CR-006"]],
    )
    objective: str = Field(
        description="Full mission objective as issued by command.",
        examples=["Scout the Nebula-9 perimeter and escort Convoy Lyra to the Anchorage."],
    )
    notes: str | None = Field(
        default=None,
        description="Operational notes and classified addenda from the commanding officer.",
        examples=["Captain Khan leads. Departure aligned with Convoy Lyra schedule."],
    )


class ErrorResponse(BaseModel):
    detail: str = Field(description="Human-readable description of the error.", examples=["Clearance denied."])


# ── Request bodies (write endpoints) ──────────────────────────

class DutyStatusUpdate(BaseModel):
    duty_status: Literal["On Duty", "Off Duty"] = Field(
        description="New duty status for the crew member.",
        examples=["Off Duty"],
    )


class InspectionUpdate(BaseModel):
    inspection_status: Literal["Inspected", "Pending Inspection", "Flagged", "Restricted"] = Field(
        description=(
            "New inspection status. One of: Inspected (cleared), Pending Inspection (awaiting review), "
            "Flagged (requires immediate review), Restricted (Admiral clearance only)."
        ),
        examples=["Inspected"],
    )


class SystemUpdate(BaseModel):
    status: str | None = Field(
        default=None,
        description="New operational status, e.g. Online, Standby, Degraded, Maintenance.",
        examples=["Online"],
    )
    health_pct: int | None = Field(
        default=None,
        description="New health percentage from 0 (failed) to 100 (optimal).",
        examples=[100],
        ge=0,
        le=100,
    )
    notes: str | None = Field(
        default=None,
        description="Updated engineering note for this system. Pass an empty string to clear it.",
        examples=["Ion storm damage repaired. Array back to full strength."],
    )


class ShipmentCreate(BaseModel):
    convoy_name: str = Field(description="Operational name of the new convoy.", examples=["Convoy Vega"])
    origin: str = Field(description="Departure station or sector.", examples=["Outpost Gamma"])
    destination: str = Field(description="Destination station or sector.", examples=["Waystation Delta"])
    eta: str | None = Field(
        default=None,
        description="Estimated time of arrival, or a status note if ETA is unavailable.",
        examples=["4 days"],
    )
    cargo_ids: list[str] = Field(
        default_factory=list,
        description="Cargo IDs to load onto this convoy.",
        examples=[["C-098", "C-333"]],
    )
    status: str = Field(
        default="Loading",
        description="Initial convoy status. One of: Loading, In Transit, Delayed, Arrived.",
        examples=["Loading"],
    )
    notes: str | None = Field(
        default=None,
        description="Operational notes from logistics command.",
        examples=["New supply run authorized by Logistics Officer Webb."],
    )


class ShipmentUpdate(BaseModel):
    status: str | None = Field(
        default=None,
        description="Updated convoy status. One of: Loading, In Transit, Delayed, Arrived.",
        examples=["In Transit"],
    )
    eta: str | None = Field(default=None, description="Updated estimated time of arrival.", examples=["2 days"])
    delay_reason: str | None = Field(
        default=None,
        description="Reason for delay if the convoy is delayed.",
        examples=["Rerouted around ion storm."],
    )
    cargo_ids: list[str] | None = Field(
        default=None,
        description="Replacement list of cargo IDs aboard this convoy.",
        examples=[["C-098"]],
    )
    notes: str | None = Field(
        default=None,
        description="Updated operational notes.",
        examples=["Back under way after checkpoint clearance."],
    )


class TradeManifestStatusUpdate(BaseModel):
    status: Literal["Active", "Completed", "Pending"] = Field(
        description="New contract status. One of: Active, Completed, Pending.",
        examples=["Completed"],
    )
    notes: str | None = Field(
        default=None,
        description="Updated contract notes from the managing officer.",
        examples=["Contract settled in full this cycle."],
    )


class MissionUpdate(BaseModel):
    status: str | None = Field(
        default=None,
        description="Updated mission status. One of: Active, Completed, Aborted.",
        examples=["Completed"],
    )
    notes: str | None = Field(
        default=None,
        description="Updated commanding officer notes for this mission.",
        examples=["Objective achieved. Returning to Outpost Gamma."],
    )


# ──────────────────────────────────────────────────────────────
# 4.  APP + OPENAPI METADATA
# ──────────────────────────────────────────────────────────────

_APP_DESCRIPTION = """
Official operational API for **Galactic Logistics**, a deep-space logistics company
on the frontier of explored space.

This API provides crew, command, and partner systems with access to Gamma station health data,
cargo manifests, shipment tracking, trade contracts, and classified fleet operations.

---

## Authentication & Clearance

All endpoints (except `/v1/whoami`) require a **Bearer token**. Pass your clearance token
in the `Authorization` header:

```
Authorization: Bearer <your-token>
```

### Clearance Levels

| Level | Role | Access |
|---|---|---|
| 1 | Deckhand | Station status, systems, crew roster, cargo manifest |
| 2 | Logistics Officer | + Crew details, cargo details, shipments, trade manifests |
| 3 | Sector Admiral | + Fleet orders, classified missions |

---

## Entity Overview

| Entity | Description |
|---|---|
| **Station** | Overall station health and individual system diagnostics |
| **Crew** | Personnel roster with roles, certifications, and duty status |
| **Cargo** | All cargo items with hazard classifications and inspection status |
| **Shipments** | Active and completed convoys with routing and delay information |
| **Trade** | Inter-faction commercial contracts and credit values |
| **Fleet** | Classified strategic orders and active mission briefings |
"""

_OPENAPI_TAGS = [
    {
        "name": "identity",
        "description": "Caller identity and clearance verification. Always available without authentication.",
    },
    {
        "name": "station",
        "description": "Station-wide status and individual subsystem health. Requires Deckhand clearance (level 1+).",
    },
    {
        "name": "crew",
        "description": "Personnel roster, roles, certifications, and duty status. Roster requires level 1+; full details require level 2+.",
    },
    {
        "name": "cargo",
        "description": (
            "Cargo manifest and per-item details including hazard classification and inspection status. "
            "Manifest (IDs and names) requires level 1+; full item details require level 2+."
        ),
    },
    {
        "name": "shipments",
        "description": "Convoy and shipment tracking — status, routing, delays, and cargo manifests. Requires Logistics Officer clearance (level 2+).",
    },
    {
        "name": "trade",
        "description": "Inter-faction trade contracts and commercial agreements. Requires Logistics Officer clearance (level 2+).",
    },
    {
        "name": "fleet",
        "description": (
            "Classified fleet orders and active mission briefings. "
            "Strictly requires Sector Admiral clearance (level 3)."
        ),
    },
]

app = FastAPI(
    title="Galactic Logistics API",
    description=_APP_DESCRIPTION,
    version="2.0.0",
    openapi_tags=_OPENAPI_TAGS,
)

BASE_DIR = FilePath(__file__).resolve().parent
SITE_DIR = BASE_DIR / "site"
DOCS_DIR = BASE_DIR / "docs"
app.mount(
    "/assets",
    StaticFiles(directory=SITE_DIR / "assets"),
    name="site-assets",
)

_COMMON_ERRORS: dict = {
    401: {"model": ErrorResponse, "description": "Missing or invalid clearance token"},
    403: {"model": ErrorResponse, "description": "Insufficient clearance level for this endpoint"},
}


# ──────────────────────────────────────────────────────────────
# 5.  ENDPOINTS
# ──────────────────────────────────────────────────────────────

# ── Identity ──────────────────────────────────────────────────

@app.get(
    "/v1/whoami",
    operation_id="whoami",
    tags=["identity"],
    summary="Return the caller's role and clearance level",
    description=(
        "Returns the role name and numeric clearance level associated with the presented Bearer token. "
        "Call this first to confirm which token you are using and what data you are authorized to access. "
        "Returns Anonymous_Public (level 0) if no token is provided, or Unknown_Token (level 0) "
        "if an unrecognized token is provided — this endpoint never returns an error."
    ),
    response_description="The caller's role name and clearance level.",
    response_model=WhoAmI,
)
async def whoami(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> WhoAmI:
    if credentials is None:
        return WhoAmI(role="Anonymous_Public", level=0)
    user_info = ROLE_HIERARCHY.get(credentials.credentials)
    if not user_info:
        return WhoAmI(role="Unknown_Token", level=0)
    return WhoAmI(role=user_info["role"], level=user_info["level"])


# ── Station ───────────────────────────────────────────────────

@app.get(
    "/v1/station/status",
    operation_id="get_station_status",
    tags=["station"],
    summary="Get overall station status",
    description=(
        "Retrieves the top-level health summary for Outpost Gamma, including oxygen levels, "
        "external weather conditions, and the current operational alert level. "
        "Use this when asked about general station safety, environmental conditions, or alert state. "
        "For individual system diagnostics, call get_station_systems instead."
    ),
    response_description="Current station location, oxygen levels, external weather, and alert level.",
    response_model=StationStatus,
    responses={**_COMMON_ERRORS},
)
async def get_station_status(
    _user: Annotated[dict, Depends(require_level(1))],
) -> StationStatus:
    return StationStatus(**STATION_STATUS)


@app.get(
    "/v1/station/systems",
    operation_id="get_station_systems",
    tags=["station"],
    summary="List all station subsystems and their health",
    description=(
        "Returns a diagnostic report for every station subsystem — life support, navigation, "
        "weapons, communications, cargo bay, engines, and shields — including operational status "
        "and health percentage. Use this when asked which systems are degraded, offline, or under maintenance, "
        "or to identify systems running below a given health threshold."
    ),
    response_description="List of all station subsystems with status and health percentage.",
    response_model=list[StationSystem],
    responses={**_COMMON_ERRORS},
)
async def get_station_systems(
    _user: Annotated[dict, Depends(require_level(1))],
) -> list[StationSystem]:
    return [StationSystem(**s) for s in STATION_SYSTEMS]


@app.patch(
    "/v1/station/systems/{system_id}",
    operation_id="update_station_system",
    tags=["station"],
    summary="Update a station subsystem's status, health, or notes",
    description=(
        "Updates the operational status, health percentage, and/or engineering notes for a single "
        "station subsystem, identified by its system ID. Only the fields you provide are changed. "
        "Use this to record that a system has been repaired, taken offline for maintenance, or that "
        "its health has changed. Returns the full updated subsystem record."
    ),
    response_description="The updated station subsystem record.",
    response_model=StationSystem,
    responses={
        **_COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "System ID not found"},
    },
)
async def update_station_system(
    system_id: Annotated[str, Path(description="System identifier, e.g. SYS-04")],
    update: SystemUpdate,
    _user: Annotated[dict, Depends(require_level(1))],
) -> StationSystem:
    system = next((s for s in STATION_SYSTEMS if s["system_id"] == system_id.upper()), None)
    if not system:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"System ID '{system_id}' not found.",
        )
    system.update(update.model_dump(exclude_unset=True))
    return StationSystem(**system)


# ── Crew ──────────────────────────────────────────────────────

@app.get(
    "/v1/crew",
    operation_id="list_crew",
    tags=["crew"],
    summary="List all crew members and their duty status",
    description=(
        "Returns a lightweight roster of all crew members aboard Outpost Gamma: name, role, and "
        "current duty status (On Duty / Off Duty). Use this to find out who is currently on duty, "
        "how many crew members are available, or to look up a crew ID by name. "
        "For certifications, clearance level, and full personnel notes, call get_crew_member with the crew ID."
    ),
    response_description="List of all crew members with name, role, and duty status.",
    response_model=list[CrewSummary],
    responses={**_COMMON_ERRORS},
)
async def list_crew(
    _user: Annotated[dict, Depends(require_level(1))],
) -> list[CrewSummary]:
    return [
        CrewSummary(crew_id=c["crew_id"], name=c["name"], role=c["role"], duty_status=c["duty_status"])
        for c in CREW.values()
    ]


@app.get(
    "/v1/crew/{crew_id}",
    operation_id="get_crew_member",
    tags=["crew"],
    summary="Get full details for a specific crew member",
    description=(
        "Retrieves the complete personnel record for a single crew member by their ID, including "
        "clearance level, all certifications, duty status, and commanding officer notes. "
        "Use this when asked about a specific person's qualifications, whether someone is authorized "
        "to handle a particular cargo type, or their current assignment. "
        "Call list_crew first to resolve a name to a crew ID."
    ),
    response_description="Full personnel record including clearance level, certifications, and notes.",
    response_model=CrewMember,
    responses={
        **_COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Crew ID not found"},
    },
)
async def get_crew_member(
    crew_id: Annotated[str, Path(description="Crew member identifier, e.g. CR-002")],
    _user: Annotated[dict, Depends(require_level(2))],
) -> CrewMember:
    member = CREW.get(crew_id.upper())
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crew ID '{crew_id}' not found.",
        )
    return CrewMember(**member)


@app.patch(
    "/v1/crew/{crew_id}/duty-status",
    operation_id="update_crew_duty_status",
    tags=["crew"],
    summary="Set a crew member On or Off Duty",
    description=(
        "Updates the duty status of a single crew member to either 'On Duty' or 'Off Duty', "
        "identified by their crew ID. Use this to put a crew member on rotation or stand them down. "
        "Returns the full updated personnel record. Call list_crew first to resolve a name to a crew ID."
    ),
    response_description="The updated crew member record with the new duty status.",
    response_model=CrewMember,
    responses={
        **_COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Crew ID not found"},
    },
)
async def update_crew_duty_status(
    crew_id: Annotated[str, Path(description="Crew member identifier, e.g. CR-002")],
    update: DutyStatusUpdate,
    _user: Annotated[dict, Depends(require_level(2))],
) -> CrewMember:
    member = CREW.get(crew_id.upper())
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crew ID '{crew_id}' not found.",
        )
    member["duty_status"] = update.duty_status
    return CrewMember(**member)


# ── Cargo ─────────────────────────────────────────────────────

@app.get(
    "/v1/cargo/manifest",
    operation_id="get_cargo_manifest",
    tags=["cargo"],
    summary="List all cargo IDs and names",
    description=(
        "Returns a lightweight index of all cargo currently aboard the station: ID and item name only. "
        "Use this to discover what cargo exists, search for a cargo item by name, or obtain a cargo ID "
        "before calling get_cargo_item for full details. "
        "Full details (mass, hazard classification, inspection status) require Logistics Officer clearance."
    ),
    response_description="List of all cargo items with their IDs and names.",
    response_model=list[CargoSummary],
    responses={**_COMMON_ERRORS},
)
async def get_cargo_manifest(
    user: Annotated[dict, Depends(require_level(1))],
) -> list[CargoSummary]:
    items = CARGO_MANIFEST
    if user["level"] < 3:
        items = [c for c in items if c["id"] not in CLASSIFIED_CARGO_IDS]
    return [CargoSummary(**c) for c in items]


@app.get(
    "/v1/cargo/{cargo_id}",
    operation_id="get_cargo_item",
    tags=["cargo"],
    summary="Get full details for a specific cargo item",
    description=(
        "Retrieves the complete record for a single cargo item by its ID, including total mass, "
        "hazard classification, operational category, inspection status, origin, and destination. "
        "Use this when asked about a specific item's danger level, whether it has been inspected, "
        "or where it came from and where it is headed. "
        "Call get_cargo_manifest first if you need to resolve an item name to a cargo ID."
    ),
    response_description="Full cargo item record including mass, hazard, category, and inspection status.",
    response_model=CargoItem,
    responses={
        **_COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Cargo ID not found"},
    },
)
async def get_cargo_item(
    cargo_id: Annotated[str, Path(description="Cargo identifier, e.g. C-421")],
    user: Annotated[dict, Depends(require_level(2))],
) -> CargoItem:
    item = CARGO_DETAILS.get(cargo_id.upper())
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cargo ID '{cargo_id}' not found.",
        )
    if item["id"] in CLASSIFIED_CARGO_IDS and user["level"] < 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cargo '{item['id']}' is Admiral-classified. Level 3 clearance required.",
        )
    return CargoItem(**item)


@app.patch(
    "/v1/cargo/{cargo_id}/inspection",
    operation_id="update_cargo_inspection",
    tags=["cargo"],
    summary="Update a cargo item's inspection status",
    description=(
        "Updates the inspection status of a single cargo item, identified by its cargo ID. "
        "Use this to clear an item as Inspected, mark it Pending Inspection, Flagged, or Restricted. "
        "Returns the full updated cargo record. Admiral-classified cargo requires level 3 clearance."
    ),
    response_description="The updated cargo item record with the new inspection status.",
    response_model=CargoItem,
    responses={
        **_COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Cargo ID not found"},
    },
)
async def update_cargo_inspection(
    cargo_id: Annotated[str, Path(description="Cargo identifier, e.g. C-421")],
    update: InspectionUpdate,
    user: Annotated[dict, Depends(require_level(2))],
) -> CargoItem:
    item = CARGO_DETAILS.get(cargo_id.upper())
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cargo ID '{cargo_id}' not found.",
        )
    if item["id"] in CLASSIFIED_CARGO_IDS and user["level"] < 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cargo '{item['id']}' is Admiral-classified. Level 3 clearance required.",
        )
    item["inspection_status"] = update.inspection_status
    return CargoItem(**item)


# ── Shipments ─────────────────────────────────────────────────

@app.get(
    "/v1/shipments",
    operation_id="list_shipments",
    tags=["shipments"],
    summary="List all convoys and their current status",
    description=(
        "Returns a summary of all convoys — active, delayed, loading, and recently arrived — "
        "including their origin, destination, ETA, and cargo IDs. "
        "Use this when asked about shipments in transit, which convoys are delayed, or what cargo "
        "is currently en route to a specific destination. "
        "For delay reasons and full operational notes, call get_shipment with the shipment ID."
    ),
    response_description="List of all convoys with status, routing, ETA, and cargo IDs.",
    response_model=list[ShipmentSummary],
    responses={**_COMMON_ERRORS},
)
async def list_shipments(
    user: Annotated[dict, Depends(require_level(2))],
) -> list[ShipmentSummary]:
    items = SHIPMENTS.values()
    if user["level"] < 3:
        items = [s for s in items if s["shipment_id"] not in CLASSIFIED_SHIPMENT_IDS]
    return [ShipmentSummary(**s) for s in items]


@app.get(
    "/v1/shipments/{shipment_id}",
    operation_id="get_shipment",
    tags=["shipments"],
    summary="Get full details for a specific convoy",
    description=(
        "Retrieves the complete record for a single convoy by its shipment ID, including the delay reason "
        "(if applicable) and full operational notes from logistics command. "
        "Use this when you need to understand why a convoy is delayed, get the full cargo manifest for "
        "a specific shipment, or read command notes on a particular convoy. "
        "Call list_shipments first to discover available shipment IDs."
    ),
    response_description="Full convoy record including delay reason and operational notes.",
    response_model=ShipmentDetail,
    responses={
        **_COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Shipment ID not found"},
    },
)
async def get_shipment(
    shipment_id: Annotated[str, Path(description="Shipment identifier, e.g. SH-002")],
    user: Annotated[dict, Depends(require_level(2))],
) -> ShipmentDetail:
    shipment = SHIPMENTS.get(shipment_id.upper())
    if not shipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shipment ID '{shipment_id}' not found.",
        )
    if shipment["shipment_id"] in CLASSIFIED_SHIPMENT_IDS and user["level"] < 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Shipment '{shipment['shipment_id']}' is Admiral-classified. Level 3 clearance required.",
        )
    return ShipmentDetail(**shipment)


@app.post(
    "/v1/shipments",
    operation_id="create_shipment",
    tags=["shipments"],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new convoy",
    description=(
        "Registers a new convoy and returns its full record, including the server-assigned shipment ID "
        "(next available SH-NNN). Use this to dispatch a new supply run or shipment. "
        "Provide the convoy name, origin, destination, and the cargo IDs to load; ETA, status, and notes "
        "are optional. Requires Logistics Officer clearance (level 2+)."
    ),
    response_description="The newly created convoy record, including its assigned shipment ID.",
    response_model=ShipmentDetail,
    responses={**_COMMON_ERRORS},
)
async def create_shipment(
    new_shipment: ShipmentCreate,
    _user: Annotated[dict, Depends(require_level(2))],
) -> ShipmentDetail:
    next_num = max((int(sid.split("-")[1]) for sid in SHIPMENTS), default=0) + 1
    shipment_id = f"SH-{next_num:03d}"
    record = {
        "shipment_id": shipment_id,
        "convoy_name": new_shipment.convoy_name,
        "status": new_shipment.status,
        "origin": new_shipment.origin,
        "destination": new_shipment.destination,
        "eta": new_shipment.eta,
        "cargo_ids": new_shipment.cargo_ids,
        "delay_reason": None,
        "notes": new_shipment.notes,
    }
    SHIPMENTS[shipment_id] = record
    return ShipmentDetail(**record)


@app.patch(
    "/v1/shipments/{shipment_id}",
    operation_id="update_shipment",
    tags=["shipments"],
    summary="Update a convoy's status, ETA, delay, cargo, or notes",
    description=(
        "Updates an existing convoy, identified by its shipment ID. Only the fields you provide are "
        "changed. Use this to mark a convoy as In Transit or Arrived, record a delay and its reason, "
        "adjust the ETA, or update the cargo manifest. Returns the full updated convoy record. "
        "Admiral-classified shipments require level 3 clearance."
    ),
    response_description="The updated convoy record.",
    response_model=ShipmentDetail,
    responses={
        **_COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Shipment ID not found"},
    },
)
async def update_shipment(
    shipment_id: Annotated[str, Path(description="Shipment identifier, e.g. SH-002")],
    update: ShipmentUpdate,
    user: Annotated[dict, Depends(require_level(2))],
) -> ShipmentDetail:
    shipment = SHIPMENTS.get(shipment_id.upper())
    if not shipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shipment ID '{shipment_id}' not found.",
        )
    if shipment["shipment_id"] in CLASSIFIED_SHIPMENT_IDS and user["level"] < 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Shipment '{shipment['shipment_id']}' is Admiral-classified. Level 3 clearance required.",
        )
    shipment.update(update.model_dump(exclude_unset=True))
    return ShipmentDetail(**shipment)


@app.delete(
    "/v1/shipments/{shipment_id}",
    operation_id="delete_shipment",
    tags=["shipments"],
    summary="Cancel and remove a convoy",
    description=(
        "Permanently removes a convoy from the registry, identified by its shipment ID. "
        "Use this to cancel a shipment. This is a destructive operation and strictly requires "
        "Sector Admiral clearance (level 3). Returns a confirmation of the removed shipment."
    ),
    response_description="Confirmation that the convoy was removed.",
    responses={
        **_COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Shipment ID not found"},
    },
)
async def delete_shipment(
    shipment_id: Annotated[str, Path(description="Shipment identifier, e.g. SH-002")],
    _user: Annotated[dict, Depends(require_level(3))],
) -> dict:
    removed = SHIPMENTS.pop(shipment_id.upper(), None)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shipment ID '{shipment_id}' not found.",
        )
    return {"status": "deleted", "shipment_id": removed["shipment_id"]}


# ── Trade ─────────────────────────────────────────────────────

@app.get(
    "/v1/trade/manifests",
    operation_id="list_trade_manifests",
    tags=["trade"],
    summary="List all trade contracts and their status",
    description=(
        "Returns a summary of all inter-faction trade contracts, including counterparty, status, "
        "a brief description of what is being exchanged, and the total credit value. "
        "Use this when asked about ongoing trade agreements, total trade value, which contracts are "
        "active or pending, or which factions Outpost Gamma is trading with. "
        "For cargo IDs and full contract notes, call get_trade_manifest with the manifest ID."
    ),
    response_description="List of all trade contracts with counterparty, status, and credit value.",
    response_model=list[TradeManifestSummary],
    responses={**_COMMON_ERRORS},
)
async def list_trade_manifests(
    user: Annotated[dict, Depends(require_level(2))],
) -> list[TradeManifestSummary]:
    items = TRADE_MANIFESTS.values()
    if user["level"] < 3:
        items = [m for m in items if m["manifest_id"] not in CLASSIFIED_MANIFEST_IDS]
    return [TradeManifestSummary(**m) for m in items]


@app.get(
    "/v1/trade/manifests/{manifest_id}",
    operation_id="get_trade_manifest",
    tags=["trade"],
    summary="Get full details for a specific trade contract",
    description=(
        "Retrieves the complete record for a single trade contract by its manifest ID, including "
        "the specific cargo IDs involved and full contract notes from the managing officer. "
        "Use this when you need to know exactly which cargo is tied to a given contract, "
        "when a contract expires, or who is managing the relationship with a trading partner. "
        "Call list_trade_manifests first to discover available manifest IDs."
    ),
    response_description="Full trade contract record including cargo IDs and management notes.",
    response_model=TradeManifestDetail,
    responses={
        **_COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Manifest ID not found"},
    },
)
async def get_trade_manifest(
    manifest_id: Annotated[str, Path(description="Trade manifest identifier, e.g. TM-001")],
    user: Annotated[dict, Depends(require_level(2))],
) -> TradeManifestDetail:
    manifest = TRADE_MANIFESTS.get(manifest_id.upper())
    if not manifest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Manifest ID '{manifest_id}' not found.",
        )
    if manifest["manifest_id"] in CLASSIFIED_MANIFEST_IDS and user["level"] < 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Trade manifest '{manifest['manifest_id']}' is Admiral-classified. Level 3 clearance required.",
        )
    return TradeManifestDetail(**manifest)


@app.patch(
    "/v1/trade/manifests/{manifest_id}",
    operation_id="update_trade_manifest",
    tags=["trade"],
    summary="Update a trade contract's status and notes",
    description=(
        "Updates the status (Active, Completed, or Pending) and optionally the notes of a single "
        "trade contract, identified by its manifest ID. Use this to settle a contract, reactivate it, "
        "or move it back to pending review. Returns the full updated contract record. "
        "Admiral-classified manifests require level 3 clearance."
    ),
    response_description="The updated trade contract record.",
    response_model=TradeManifestDetail,
    responses={
        **_COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Manifest ID not found"},
    },
)
async def update_trade_manifest(
    manifest_id: Annotated[str, Path(description="Trade manifest identifier, e.g. TM-001")],
    update: TradeManifestStatusUpdate,
    user: Annotated[dict, Depends(require_level(2))],
) -> TradeManifestDetail:
    manifest = TRADE_MANIFESTS.get(manifest_id.upper())
    if not manifest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Manifest ID '{manifest_id}' not found.",
        )
    if manifest["manifest_id"] in CLASSIFIED_MANIFEST_IDS and user["level"] < 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Trade manifest '{manifest['manifest_id']}' is Admiral-classified. Level 3 clearance required.",
        )
    manifest.update(update.model_dump(exclude_unset=True))
    return TradeManifestDetail(**manifest)


# ── Fleet ─────────────────────────────────────────────────────

@app.get(
    "/v1/fleet/orders",
    operation_id="get_fleet_orders",
    tags=["fleet"],
    summary="Get classified fleet orders from High Command",
    description=(
        "Retrieves the current strategic fleet orders issued by High Command, including the primary "
        "and secondary mission objectives, rules of engagement, and priority cargo designations. "
        "Use this when asked about the station's real mission, target sector, strategic objectives, "
        "what cargo is considered mission-critical, or the current rules of engagement. "
        "Strictly requires Sector Admiral clearance (level 3)."
    ),
    response_description="Current fleet orders including objectives, rules of engagement, and priority cargo.",
    response_model=FleetOrders,
    responses={**_COMMON_ERRORS},
)
async def get_fleet_orders(
    _user: Annotated[dict, Depends(require_level(3))],
) -> FleetOrders:
    return FleetOrders(**FLEET_ORDERS)


@app.get(
    "/v1/fleet/missions",
    operation_id="list_missions",
    tags=["fleet"],
    summary="List all fleet missions and their status",
    description=(
        "Returns a summary of all fleet missions — active, completed, and classified — including "
        "the mission name, target sector, status, and assigned crew IDs. "
        "Use this when asked which missions are currently active, which crew members are on assignment, "
        "or what operations have been completed. "
        "For full mission objectives and classified notes, call get_mission with the mission ID. "
        "Strictly requires Sector Admiral clearance (level 3)."
    ),
    response_description="List of all missions with status, target sector, and assigned crew.",
    response_model=list[MissionSummary],
    responses={**_COMMON_ERRORS},
)
async def list_missions(
    _user: Annotated[dict, Depends(require_level(3))],
) -> list[MissionSummary]:
    return [MissionSummary(**m) for m in MISSIONS.values()]


@app.get(
    "/v1/fleet/missions/{mission_id}",
    operation_id="get_mission",
    tags=["fleet"],
    summary="Get the full briefing for a specific mission",
    description=(
        "Retrieves the complete mission briefing for a single fleet operation by its mission ID, "
        "including the full objective text and classified commanding officer notes. "
        "Use this when asked for the details of a specific mission, who leads it, "
        "what the exact objectives are, or any classified addenda. "
        "Call list_missions first to discover available mission IDs. "
        "Strictly requires Sector Admiral clearance (level 3)."
    ),
    response_description="Full mission briefing including objectives and classified notes.",
    response_model=MissionDetail,
    responses={
        **_COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Mission ID not found"},
    },
)
async def get_mission(
    mission_id: Annotated[str, Path(description="Mission identifier, e.g. MISSION-ALPHA")],
    _user: Annotated[dict, Depends(require_level(3))],
) -> MissionDetail:
    mission = MISSIONS.get(mission_id.upper())
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission ID '{mission_id}' not found.",
        )
    return MissionDetail(**mission)


@app.patch(
    "/v1/fleet/missions/{mission_id}",
    operation_id="update_mission",
    tags=["fleet"],
    summary="Update a mission's status or notes",
    description=(
        "Updates the status (Active, Completed, or Aborted) and/or commanding officer notes of a single "
        "fleet mission, identified by its mission ID. Only the fields you provide are changed. "
        "Use this to mark a mission complete or aborted, or to append operational notes. "
        "Returns the full updated mission briefing. Strictly requires Sector Admiral clearance (level 3)."
    ),
    response_description="The updated mission briefing.",
    response_model=MissionDetail,
    responses={
        **_COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Mission ID not found"},
    },
)
async def update_mission(
    mission_id: Annotated[str, Path(description="Mission identifier, e.g. MISSION-ALPHA")],
    update: MissionUpdate,
    _user: Annotated[dict, Depends(require_level(3))],
) -> MissionDetail:
    mission = MISSIONS.get(mission_id.upper())
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission ID '{mission_id}' not found.",
        )
    mission.update(update.model_dump(exclude_unset=True))
    return MissionDetail(**mission)


# ── Operational (excluded from OpenAPI schema) ────────────────

@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}


@app.get("/styles.css", include_in_schema=False)
async def site_styles() -> FileResponse:
    return FileResponse(SITE_DIR / "styles.css")


@app.get("/app.js", include_in_schema=False)
async def site_script() -> FileResponse:
    return FileResponse(SITE_DIR / "app.js")


@app.get("/api-onboarding.pdf", include_in_schema=False)
async def api_onboarding_pdf() -> FileResponse:
    return FileResponse(
        DOCS_DIR / "Galactic-Logistics-API-Onboarding.pdf",
        media_type="application/pdf",
        filename="Galactic-Logistics-API-Onboarding.pdf",
    )


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(SITE_DIR / "index.html")


# Unlisted maintenance hook. Restores the in-memory store to its seed baseline,
# discarding everything written via the POST/PATCH/DELETE endpoints. Kept out of
# the OpenAPI schema (include_in_schema=False) and gated by a dedicated secret
# header (X-Reset-Key, compared to env RESET_KEY) that is independent of the
# clearance tokens — deliberately not documented in the served API description.
_RESET_KEY = os.environ.get("RESET_KEY", "reset-outpost-gamma")


@app.post("/v1/internal/reset", include_in_schema=False)
async def reset_database(
    x_reset_key: Annotated[str | None, Header()] = None,
) -> dict:
    if x_reset_key != _RESET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing reset key.",
        )
    reset_state()
    return {
        "status": "reset",
        "crew": len(CREW),
        "cargo": len(CARGO_DETAILS),
        "shipments": len(SHIPMENTS),
        "trade_manifests": len(TRADE_MANIFESTS),
        "missions": len(MISSIONS),
    }
