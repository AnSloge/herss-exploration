"""Instance definitions for the pump-audit replica, transcribed from the
topology / start_state files under analysis/pump_audit/inst_*/ ."""
from replica_pump import Params, Reservoir, Pstation, Pump, Channel


def inst_min():
    nodes = {
        0: Pump(0, "pump_AB", source=3, target=1, inlet_masl=50.0,
                max_discharge=2.0, headlosscoef=0.0, motor_eff=1.0,
                startstop=0.0, uniform_curve=[80.0] * 11),
        1: Reservoir(1, "reservoir_A", HRW=110.0, LRW=100.0, res_penalty=300,
                     curve_masl=[99, 100, 110, 111], curve_Mm3=[9.0, 10.0, 20.0, 21.0],
                     ovfl_masl=[110, 111, 112], ovfl_m3s=[0.0, 10.0, 60.0], ovfl_to=4,
                     tunnel_to=2),
        2: Pstation(2, "pstation_A", downlink_to=3,
                    curve_Q=[0.0, 1.0, 2.0], curve_psnt=[0.1, 40.0, 80.0],
                    max_discharge=2.0, gen_eff=1.0, headlosscoef=0.0,
                    powstat_masl=55.0, startstop=0.0, e_eq=0.1090),
        3: Reservoir(3, "reservoir_B", HRW=60.0, LRW=50.0, res_penalty=300,
                     curve_masl=[49, 50, 60, 61], curve_Mm3=[9.0, 10.0, 20.0, 21.0],
                     ovfl_masl=[60, 61, 62], ovfl_m3s=[0.0, 10.0, 60.0], ovfl_to=4,
                     tunnel_to=None, hatch_to=4, hatch_minQ=0.0, hatch_maxQ=2.0,
                     hatch_masl=50.0),
        4: Channel(4, "elv", downstream_to=-9, n_linres=3, k_hours=1),
    }
    return Params(dt=3600, nodes=nodes, restprice=40.0), {4: [0.0, 0.0, 0.0]}


def inst_fixture():
    nodes = {
        0: Pump(0, "pump_AB", source=3, target=1, inlet_masl=61.0,
                max_discharge=2.0, headlosscoef=0.05, motor_eff=0.97,
                startstop=100.0,
                uniform_curve=[0, 40, 65, 80, 88, 92, 92, 90, 87, 83, 78]),
        1: Reservoir(1, "reservoir_A", HRW=110.0, LRW=90.0, res_penalty=300,
                     curve_masl=[89, 90, 100, 110, 115],
                     curve_Mm3=[0.0, 5.0, 20.0, 40.0, 60.0],
                     ovfl_masl=[110, 112, 115], ovfl_m3s=[0.0, 10.0, 60.0], ovfl_to=4,
                     tunnel_to=2),
        2: Pstation(2, "pstation_A", downlink_to=3,
                    curve_Q=[0.00, 0.50, 0.86, 1.14, 1.40, 1.60, 1.74, 1.84, 1.90, 2.00],
                    curve_psnt=[0, 50, 80, 90, 93, 93, 93, 92, 91, 88],
                    max_discharge=2.0, gen_eff=0.96, headlosscoef=0.1,
                    powstat_masl=70.0, startstop=0.0, e_eq=0.0785),
        3: Reservoir(3, "reservoir_B", HRW=75.0, LRW=60.0, res_penalty=300,
                     curve_masl=[59, 60, 65, 75, 80],
                     curve_Mm3=[0.0, 3.0, 8.0, 15.0, 25.0],
                     ovfl_masl=[75, 78, 80], ovfl_m3s=[0.0, 5.0, 20.0], ovfl_to=4,
                     tunnel_to=None, hatch_to=4, hatch_minQ=0.0, hatch_maxQ=3.0,
                     hatch_masl=60.0),
        4: Channel(4, "elv", downstream_to=-9, n_linres=3, k_hours=4),
    }
    return Params(dt=86400, nodes=nodes, restprice=30.0), {4: [0.001, 0.001, 0.001]}
