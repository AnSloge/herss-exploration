#!/usr/bin/env python
"""
Reader for the per-step node output files HERSS writes when WRITE_NODEFILES is 1.

These files are the validation surface for replica3. One CLI run writes a full
per-step trace for every node -- level, storage, inflow, outflow, head, power,
each cost component -- which is both richer and far cheaper than pulling the
same arrays back through cppyy one `double*` at a time in a subprocess each
(see oracle3's module docstring on the LowLevelView segfault).

File layout is the same for all three node types (reservoir.cpp:1182-1193,
powerstation.cpp:717-741, channel.cpp:444-453): some metadata lines, a units
header, a column-name header, then one row per timestep. Both header lines start
with "yyyy mm dd hh"; the column-name header is the last of them. The first four
columns are the date, so column name i maps to field index i+4.
"""

import os


def _read(path):
    with open(path) as f:
        return [l.rstrip("\n") for l in f if l.strip()]


def read_node_file(path):
    """
    {'meta': [str], 'columns': [str], 'rows': [[str]]} for one node output file.
    """
    lines = _read(path)
    hdr_idx = [i for i, l in enumerate(lines) if l.startswith("yyyy mm dd hh")]
    if not hdr_idx:
        raise ValueError(f"no column header in {path}")
    h = hdr_idx[-1]
    columns = lines[h].split()[4:]
    rows = [l.split() for l in lines[h + 1:]]
    return {"meta": lines[:hdr_idx[0]], "columns": columns, "rows": rows}


def column(node, name):
    """One column as a list of floats, by column name."""
    try:
        j = node["columns"].index(name) + 4
    except ValueError:
        raise KeyError(f"{name!r} not among {node['columns']}") from None
    return [float(r[j]) for r in node["rows"]]


def load_all(output_dir, p):
    """
    {idnr: node dict} for every node of a SystemParams, read from output_dir.

    File names are node<idnr>_<NAME>.txt (reservoir.cpp:1170, powerstation.cpp:706,
    channel.cpp:431).
    """
    out = {}
    for group in (p.reservoirs, p.stations, p.channels):
        for n in group:
            path = os.path.join(output_dir, f"node{n.idnr}_{n.name}.txt")
            out[n.idnr] = read_node_file(path)
    return out


def trace(output_dir, p):
    """
    Per-step traces keyed (idnr, field), using the replica's own field names.

    Only the fields the replica actually produces are extracted; anything else in
    the file is left alone.
    """
    nodes = load_all(output_dir, p)
    tr = {}
    for r in p.reservoirs:
        n = nodes[r.idnr]
        tr[(r.idnr, "res_Mm3")] = column(n, "Res_Mm3")
        tr[(r.idnr, "res_masl")] = column(n, "Res_masl")
        tr[(r.idnr, "res_fr")] = column(n, "Res_fr")
        tr[(r.idnr, "up_inflow_m3s")] = column(n, "Up_Inflow")
        tr[(r.idnr, "tunnelflow_m3s")] = column(n, "tunnelflow")
        tr[(r.idnr, "overflow_m3s")] = column(n, "overflow")
        tr[(r.idnr, "lrw_cost")] = column(n, "lrw_cost")
    for s in p.stations:
        n = nodes[s.idnr]
        tr[(s.idnr, "up_inflow_m3s")] = column(n, "Up_Inflow")
        tr[(s.idnr, "tot_outflow_m3s")] = column(n, "tot_outflow")
        tr[(s.idnr, "Hbrutto")] = column(n, "Hbrutto")
        tr[(s.idnr, "Hnetto")] = column(n, "Hnetto")
        tr[(s.idnr, "power_MWh")] = column(n, "Power")
        tr[(s.idnr, "income")] = column(n, "income")
        tr[(s.idnr, "startstop_cost")] = column(n, "startstopCost")
        tr[(s.idnr, "aggressive_cost")] = column(n, "cost_aggressive_actions")
        tr[(s.idnr, "profit")] = column(n, "profit")
    for c in p.channels:
        n = nodes[c.idnr]
        tr[(c.idnr, "up_inflow_m3s")] = column(n, "Up_Inflow")
        tr[(c.idnr, "storage_Mm3")] = column(n, "Storage_Mm3")
        tr[(c.idnr, "tot_outflow_m3s")] = column(n, "tot_outflow")
    return tr


RIVERSYSTEM_KEYS = (
    "start_water_Mm3", "inflow_volume_Mm3", "outflow_Mm3", "end_water_Mm3",
    "waterbalance", "valuefunction_Euro", "tot_active_remaining_Mm3",
    "tot_remaining_Mm3", "tot_remaining_MWh", "tot_remaining_Euro",
    "tot_profit_Euro", "tot_income_Euro", "tot_cost_Euro", "Sum_Production_MWh",
    "sum_aggressive_actions_cost", "sum_lrw_cost_Euro", "sum_startstopcost_Euro",
    "sum_qmin_cost_Euro", "RestPrice_Euro", "Average_price_Euro",
)


def read_riversystem(path):
    """Scalar summary block from riversystem_<SYSTEM>_output.txt."""
    out = {}
    with open(path) as f:
        for line in f:
            s = line.strip()
            for k in RIVERSYSTEM_KEYS:
                if s.startswith(k) and "=" in s:
                    out[k] = float(s.split("=")[1])
    return out
