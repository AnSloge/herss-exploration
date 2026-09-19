"""
plot_topology.py
Parse a HERSS topology.txt and render a directed graph of nodes and connections
using graphviz (Digraph).

Generalised from data/res_casc_A/plot_topology.py:
  * takes the dataset directory as an argument instead of being fixed to its own folder
  * writes the rendered graph outside data/ (CLAUDE.md sec. 5: data/* is gitignored,
    and dataset output/ folders are tracked)
  * understands the PUMP node type (src/herss.h:862, src/pump.cpp) and the
    SPILLWAY / OUTLET_AUTO_QMIN keywords used by the newer datasets

Usage
-----
    python analysis/plot_topology.py data/fabelvassdraget
    python analysis/plot_topology.py data/fabelvassdraget -o /somewhere/else

Node colours
------------
RESERVOIR  : steelblue      (cylinder shape)
PSTATION   : darkorange     (diamond shape)
CHANNEL    : mediumseagreen (ellipse shape)
PUMP       : rebeccapurple  (box3d shape)

Edge colours
------------
OVERFLOW      : dodgerblue
SPILLWAY      : dodgerblue
OUTLET_HATCH  : sienna
OUTLET_TUNNEL : slategray
AUTO_QMIN     : cadetblue
DOWNLINK      : darkorange     (power station discharge)
CHANNEL       : mediumseagreen
PUMP_INTAKE   : rebeccapurple  (source reservoir -> pump)
PUMP_LIFT     : rebeccapurple  (pump -> target reservoir)
"""

import argparse
from pathlib import Path

from graphviz import Digraph

REPO_ROOT   = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "analysis" / "topology_plots"

NODE_STYLE = {
    "RESERVOIR": dict(shape="cylinder", style="filled", fillcolor="steelblue",
                      fontcolor="white", fontname="Helvetica-Bold"),
    "PSTATION":  dict(shape="diamond",  style="filled", fillcolor="darkorange",
                      fontcolor="white", fontname="Helvetica-Bold"),
    "CHANNEL":   dict(shape="ellipse",  style="filled", fillcolor="mediumseagreen",
                      fontcolor="white", fontname="Helvetica-Bold"),
    "PUMP":      dict(shape="box3d",    style="filled", fillcolor="rebeccapurple",
                      fontcolor="white", fontname="Helvetica-Bold"),
}

EDGE_STYLE = {
    "OVERFLOW":      dict(color="dodgerblue",     xlabel="overflow",      style="dashed", fontsize="10"),
    "SPILLWAY":      dict(color="dodgerblue",     xlabel="spillway",      style="dashed", fontsize="10"),
    "OUTLET_HATCH":  dict(color="sienna",         xlabel="outlet hatch",  style="solid",  fontsize="10"),
    "OUTLET_TUNNEL": dict(color="slategray",      xlabel="outlet tunnel", style="solid",  fontsize="10"),
    "AUTO_QMIN":     dict(color="cadetblue",      xlabel="auto qmin",     style="dotted", fontsize="10"),
    "DOWNLINK":      dict(color="darkorange",     xlabel="discharge",     style="bold",   fontsize="10"),
    "CHANNEL":       dict(color="mediumseagreen", xlabel="channel flow",  style="solid",  fontsize="10"),
    "PUMP_INTAKE":   dict(color="rebeccapurple",  xlabel="pump intake",   style="bold",   fontsize="10"),
    "PUMP_LIFT":     dict(color="rebeccapurple",  xlabel="pump lift",     style="bold",   fontsize="10"),
}

INVALID_IDS = {-9999, -9}   # sentinel values meaning "no connection"


def link_target(tokens, index):
    """Return the node id at `index`, or None when the link is unused.

    A disabled link is written either as a sentinel (OUTLET_TUNNEL -9999) or by
    dropping the remaining columns altogether (OUTLET_AUTO_QMIN -9999, where the
    downstream id normally in column 2 is simply absent).
    """
    if index >= len(tokens):
        return None
    try:
        node_id = int(tokens[index])
    except ValueError:
        return None
    return None if node_id in INVALID_IDS else node_id


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def parse_topology(filepath: Path):
    """Return (nodes, edges).

    nodes : dict  id -> {"type": str, "name": str}
    edges : list  of (src_id, dst_id, link_type)
    """
    nodes = {}
    edges = []

    current = None

    with open(filepath) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            tokens = line.split()
            keyword = tokens[0].upper()

            # ---- open a new node block --------------------------------
            if keyword == "NODE":
                # NODE  RESERVOIR  0  RES_A
                # NODE  CHANNEL    2  CHAN2  5   (last token = downstream id)
                nodetype = tokens[1].upper()
                node_id  = int(tokens[2])
                name     = tokens[3]
                current  = {"id": node_id, "type": nodetype, "name": name}
                nodes[node_id] = current

                # CHANNEL carries downstream id on the NODE line
                if nodetype == "CHANNEL" and len(tokens) >= 5:
                    ds = link_target(tokens, 4)
                    if ds is not None:
                        edges.append((node_id, ds, "CHANNEL"))

            elif keyword == "ENDNODE":
                current = None

            elif current is None:
                continue   # outside any node block

            # ---- connection keywords ----------------------------------
            elif keyword == "OVERFLOW_CURVE":
                # OVERFLOW_CURVE  <npts>  <downstream_id>
                ds = link_target(tokens, 2)
                if ds is not None:
                    edges.append((current["id"], ds, "OVERFLOW"))

            elif keyword == "SPILLWAY":
                # SPILLWAY  <downstream_id>  C  L  spillway_level_masl
                # (src/reservoir.cpp:852-854)
                ds = link_target(tokens, 1)
                if ds is not None:
                    edges.append((current["id"], ds, "SPILLWAY"))

            elif keyword == "OUTLET_HATCH":
                # OUTLET_HATCH  <downstream_id>  ...
                ds = link_target(tokens, 1)
                if ds is not None:
                    edges.append((current["id"], ds, "OUTLET_HATCH"))

            elif keyword == "OUTLET_TUNNEL":
                ds = link_target(tokens, 1)
                if ds is not None:
                    edges.append((current["id"], ds, "OUTLET_TUNNEL"))

            elif keyword == "OUTLET_AUTO_QMIN":
                # OUTLET_AUTO_QMIN  <nr_periods>  <downstream_id>  <outlet_masl>
                # (src/reservoir.cpp:1003)
                ds = link_target(tokens, 2)
                if ds is not None:
                    edges.append((current["id"], ds, "AUTO_QMIN"))

            elif keyword == "DOWNLINK_IDNR":
                ds = link_target(tokens, 1)
                if ds is not None:
                    edges.append((current["id"], ds, "DOWNLINK"))

            # ---- PUMP endpoints (src/pump.cpp:496, 506) ---------------
            # A PUMP is not part of the river graph: it names its own source and
            # target reservoirs, and water flows source -> pump -> target.
            elif keyword == "PUMP_SOURCE_IDNR":
                src = link_target(tokens, 1)
                if src is not None:
                    edges.append((src, current["id"], "PUMP_INTAKE"))

            elif keyword == "PUMP_TARGET_IDNR":
                ds = link_target(tokens, 1)
                if ds is not None:
                    edges.append((current["id"], ds, "PUMP_LIFT"))

    return nodes, edges


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------
def build_graph(nodes, edges, title=None):
    dot = Digraph(
        name="Topology",
        comment="Hydro cascade topology",
        graph_attr={
            "rankdir": "TB",
            # NOT "curved": on edges that dot reverses to break a cycle, splines=curved
            # places the arrowhead at the tail instead of the head. The pump loops
            # (source -> pump -> target -> station -> source) are the only cycles in
            # these topologies, so this silently drew every pump intake backwards.
            "splines": "spline",
            "nodesep": "0.6",
            "ranksep": "0.8",
            "fontname": "Helvetica",
        },
        node_attr={"fontsize": "12"},
        edge_attr={"fontname": "Helvetica", "fontcolor": "gray30"},
    )

    if title:
        dot.graph_attr["label"] = title
        dot.graph_attr["labelloc"] = "t"
        dot.graph_attr["fontsize"] = "18"

    # Add nodes
    for node_id, info in sorted(nodes.items()):
        ntype = info["type"]
        label = f"{info['name']}\n(id={node_id})"
        style = NODE_STYLE.get(ntype, dict(shape="box", style="filled",
                                            fillcolor="lightgray"))
        dot.node(str(node_id), label=label, **style)

    # Add edges (deduplicate same src-dst-type)
    seen = set()
    for src, dst, etype in edges:
        key = (src, dst, etype)
        if key in seen:
            continue
        seen.add(key)
        style = EDGE_STYLE.get(etype, dict(color="black", label=etype,
                                            style="solid", fontsize="10"))
        dot.edge(str(src), str(dst), **style)

    return dot


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", type=Path,
                    help="dataset directory containing topology.txt, e.g. data/fabelvassdraget")
    ap.add_argument("-o", "--outdir", type=Path, default=DEFAULT_OUT,
                    help=f"directory for the rendered graph (default: {DEFAULT_OUT})")
    ap.add_argument("-f", "--format", default="png", help="output format (default: png)")
    args = ap.parse_args()

    dataset = args.dataset if args.dataset.is_dir() else args.dataset.parent
    topology_file = dataset / "topology.txt"
    if not topology_file.is_file():
        ap.error(f"no topology.txt in {dataset}")

    args.outdir.mkdir(parents=True, exist_ok=True)
    out_stem = args.outdir / f"topology_{dataset.resolve().name}"

    nodes, edges = parse_topology(topology_file)

    print(f"{topology_file}: parsed {len(nodes)} nodes and {len(edges)} edges.")
    for nid, info in sorted(nodes.items()):
        print(f"  Node {nid:3d}  {info['type']:12s}  {info['name']}")
    print()
    for src, dst, etype in edges:
        print(f"  {src} --> {dst}  [{etype}]")

    dot = build_graph(nodes, edges, title=dataset.resolve().name)
    rendered = dot.render(str(out_stem), format=args.format, cleanup=True)
    print(f"\nGraph saved to: {rendered}")


if __name__ == "__main__":
    main()
