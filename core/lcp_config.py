"""Helpers for translating GUI LCP parameters to the EMTP kernel API."""

from typing import Any, Dict, Mapping


OHL_CONFIG_KEYS = {
    "line_name",
    "freq_min",
    "freq_max",
    "n_freq",
    "ground_resistivity",
    "ground_permeability",
    "ground_permittivity",
    "phase_radius",
    "phase_dc_resistance",
    "phase_mu_r",
    "phase_bundle_n",
    "phase_bundle_spacing",
    "phase_positions",
    "gw_radius",
    "gw_dc_resistance",
    "gw_mu_r",
    "gw_positions",
    "kron_reduction",
    "Yc_poles_min",
    "Yc_poles_max",
    "Yc_target_error",
    "H_poles_min",
    "H_poles_max",
    "H_target_error",
}

OHL_GUI_KEY_MAP = {
    "n_freq_increments": "n_freq",
    "eliminate_ground_wires": "kron_reduction",
}

SINGLE_CABLE_CONFIG_KEYS = {
    "line_name",
    "line_length",
    "freq_min",
    "freq_max",
    "n_freq",
    "soil_rho",
    "soil_epsilon_r",
    "soil_mu_r",
    "Yc_poles_min",
    "Yc_poles_max",
    "Yc_target_error",
    "H_poles_min",
    "H_poles_max",
    "H_target_error",
    "enforce_passivity",
    "use_freq_dependent",
}

SINGLE_CABLE_GUI_KEY_MAP = {
    "soil_resistivity": "soil_rho",
    "soil_permittivity": "soil_epsilon_r",
    "n_freq_increments": "n_freq",
}

SINGLE_CABLE_GEOMETRY_KEYS = {
    "core_radius",
    "core_rho",
    "core_mu_r",
    "insulation_radius",
    "insulation_epsilon_r",
    "insulation_tan_delta",
    "insulation_mu_r",
    "sheath_inner_radius",
    "sheath_outer_radius",
    "sheath_rho",
    "sheath_mu_r",
    "sheath_insulation_radius",
    "sheath_insulation_epsilon_r",
    "sheath_insulation_mu_r",
    "armor_inner_radius",
    "armor_outer_radius",
    "armor_rho",
    "armor_mu_r",
    "jacket_radius",
    "jacket_epsilon_r",
    "jacket_tan_delta",
    "jacket_mu_r",
    "burial_depth",
    "horizontal_pos",
}

SINGLE_CABLE_GEOMETRY_GUI_KEY_MAP = {
    "core_resistivity": "core_rho",
    "insulation_outer_radius": "insulation_radius",
    "insulation_eps_r": "insulation_epsilon_r",
    "sheath_resistivity": "sheath_rho",
    "outer_jacket_radius": "jacket_radius",
}

THREE_CORE_CONFIG_KEYS = {
    "line_name",
    "n_inner_cables",
    "n_total_conductors",
    "line_length",
    "steady_state_freq",
    "freq_min",
    "freq_max",
    "n_freq",
    "ground_resistivity",
    "ground_permeability",
    "ground_permittivity",
    "pipe_inner_radius",
    "pipe_outer_radius",
    "pipe_rho",
    "pipe_mu_r",
    "jacket_radius",
    "pipe_inner_insulation_epsilon_r",
    "pipe_outer_insulation_epsilon_r",
    "burial_depth",
    "horizontal_pos",
    "core_radius",
    "core_rho",
    "core_mu_r",
    "insulation_radius",
    "insulation_epsilon_r",
    "sheath_outer_radius",
    "sheath_rho",
    "sheath_mu_r",
    "outer_insulation_radius",
    "outer_insulation_epsilon_r",
    "cable_angles_deg",
    "distance_from_center",
    "Yc_poles_min",
    "Yc_poles_max",
    "Yc_target_error",
    "H_poles_min",
    "H_poles_max",
    "H_target_error",
}

THREE_CORE_GUI_KEY_MAP = {
    "pipe_resistivity": "pipe_rho",
    "core_resistivity": "core_rho",
    "insulation_eps_r": "insulation_epsilon_r",
    "sheath_radius": "sheath_outer_radius",
    "sheath_resistivity": "sheath_rho",
    "dist_from_center": "distance_from_center",
    "conductor_angles": "cable_angles_deg",
    "soil_resistivity": "ground_resistivity",
    "soil_permittivity": "ground_permittivity",
    "n_freq_increments": "n_freq",
}


def build_lcp_ohl_config(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Return only fields accepted by the kernel OHLLineConfig dataclass."""
    config: Dict[str, Any] = {}

    for key in OHL_CONFIG_KEYS:
        if key in params:
            config[key] = params[key]

    for gui_key, kernel_key in OHL_GUI_KEY_MAP.items():
        if gui_key in params:
            config[kernel_key] = params[gui_key]

    return config


def build_lcp_single_cable_config(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Return fields accepted by SingleCoreCableConfig and its cable geometry."""
    config: Dict[str, Any] = {}

    for key in SINGLE_CABLE_CONFIG_KEYS:
        if key in params:
            config[key] = params[key]

    for gui_key, kernel_key in SINGLE_CABLE_GUI_KEY_MAP.items():
        if gui_key in params:
            config[kernel_key] = params[gui_key]

    cables = params.get("cables")
    if cables is None and "n_cables" in params:
        cables = [
            _default_single_cable_geometry(i, int(params.get("n_cables") or 1))
            for i in range(max(1, int(params.get("n_cables") or 1)))
        ]
    if cables is not None:
        config["cables"] = [
            _build_single_cable_geometry(cable)
            for cable in cables
        ]

    return config


def build_lcp_three_core_cable_config(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Return only fields accepted by the kernel three-core CableLineConfig."""
    config: Dict[str, Any] = {}

    for key in THREE_CORE_CONFIG_KEYS:
        if key in params:
            config[key] = params[key]

    for gui_key, kernel_key in THREE_CORE_GUI_KEY_MAP.items():
        if gui_key in params:
            config[kernel_key] = params[gui_key]

    return config


def get_lcp_ohl_conductor_count(params: Mapping[str, Any]) -> int:
    """Return the ULM conductor count expected by an overhead-line config."""
    phase_positions = params.get("phase_positions")
    gw_positions = params.get("gw_positions")
    if phase_positions is not None or gw_positions is not None:
        return len(phase_positions or []) + len(gw_positions or [])

    phase_count = int(params.get("n_phases", 2) or 0)
    gw_count = int(params.get("n_gw", 0) or 0)
    return max(1, phase_count + gw_count)


def _build_single_cable_geometry(spec: Mapping[str, Any]) -> Dict[str, Any]:
    geometry: Dict[str, Any] = {}

    for key in SINGLE_CABLE_GEOMETRY_KEYS:
        if key in spec:
            geometry[key] = spec[key]

    for gui_key, kernel_key in SINGLE_CABLE_GEOMETRY_GUI_KEY_MAP.items():
        if gui_key in spec:
            geometry[kernel_key] = spec[gui_key]

    if "sheath_inner_radius" not in geometry and "insulation_radius" in geometry:
        geometry["sheath_inner_radius"] = geometry["insulation_radius"]
    if "armor_inner_radius" not in geometry and "sheath_outer_radius" in geometry:
        geometry["armor_inner_radius"] = geometry["sheath_outer_radius"]

    return geometry


def _default_single_cable_geometry(index: int, count: int) -> Dict[str, Any]:
    spacing = 0.5
    center = (count - 1) / 2
    return _build_single_cable_geometry({
        "core_radius": 0.02,
        "core_resistivity": 1.7e-8,
        "insulation_outer_radius": 0.035,
        "insulation_eps_r": 3.5,
        "sheath_outer_radius": 0.04,
        "sheath_resistivity": 2.2e-7,
        "armor_outer_radius": 0.045,
        "outer_jacket_radius": 0.05,
        "burial_depth": 1.0,
        "horizontal_pos": (index - center) * spacing,
    })
