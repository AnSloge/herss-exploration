# Concept glossary — the HERSS river system

A plain-English reference to the parts of a regulated hydropower river system and the
quantities used to describe it. Written for a reader who knows optimization but is new
to hydropower. All figures are taken from the uTAHPS datasets.

---

### The river system

A regulated hydropower river system is a chain of lakes and rivers that has been
rebuilt so the flow of water can be controlled instead of simply running to the sea.
It consists of reservoirs that store water, power stations that convert falling water
into electricity, and river reaches and tunnels that carry water between them. Its
purpose is to move water in time: hold it back when electricity is cheap, release it
through the turbines when electricity is expensive, and avoid losing any of it over
the dam.

---

### Node

A node is one component of the system: a reservoir, a power station, or a channel.
Each node has a number, and each node points to the node it drains into, so the nodes
together form a network that runs from the mountains down to the sea. The numbering
follows one strict rule: water may only flow from a lower-numbered node to a
higher-numbered node. Nodes are processed in numerical order within each time step,
so a node always has all of its upstream water available by the time it is its turn.

---

### Reservoir

A reservoir is a lake with a dam, used to store water until it is worth using. Not all
of the water in a reservoir is usable: the dam has a lowest regulated water level
(LRW), below which the operator is not permitted to draw, and a highest regulated
water level (HRW), above which water spills over the dam. The water between those two
levels is the active storage — the only part that is actually a decision variable.
The reservoirs differ enormously in size: HJELLE holds 9 million cubic metres of
active storage between LRW at 748 metres above sea level and HRW at 757 metres, while
KROKNESVATN holds 199 million cubic metres between LRW at 333 metres and HRW at 433
metres — more than twenty times as much.

---

### Power station

A power station converts water falling from a reservoir into electricity. Water leaves
the reservoir through a tunnel, drops down to the turbines, spins them, and continues
downstream — the water is not consumed, only moved and lowered. A generator is one
turbine-and-alternator unit inside the station; each of the four uTAHPS stations has a
single generator. The action variable sets what fraction of the station's maximum
discharge is passed in that time step, where maximum discharge is the largest flow the
turbines can physically take: 4.0 cubic metres per second at SVOLETJONN, 9.8 at
EASTER.

---

### Channel

A channel is a river reach or transport tunnel that carries water from one node to the
next. It has internal storage — water that is in transit inside the reach at any
moment — but no gate and no controllable outlet, so nothing about a channel is a
decision. Water put in at the top emerges at the bottom spread out over time rather
than all at once, which both delays the flow and smooths its peaks. How long the trip
takes depends on the length and steepness of the reach: in uTAHPS the travel times
range from 1 hour through GRONANI to 6 hours through DALSANA.

---

### Hatch

A hatch is a controllable gate low in the dam wall that releases water from the
reservoir straight into the river below, bypassing the tunnel to the power station.
Like a power station, it takes an action between 0 and 1, which sets the gate opening
between its minimum and maximum flow. It only works when the reservoir level is above
the gate's sill, since below that there is no water at the gate. It is used to move
water when producing electricity is not the goal — to draw a reservoir down ahead of a
flood, or to meet a required flow in the river below the dam. None of the four uTAHPS
reservoirs uses a hatch; all of them release only through the tunnel.

---

### Cascade

A cascade is a set of reservoirs and power stations arranged one below the other on
the same watercourse, so that everything released from an upper reservoir eventually
arrives as inflow at the next reservoir down. In uTAHPS, water released through
SVOLETJONN flows down to GRESSE, and water from both SVEIGSHYL stations flows down to
KROKNESVATN. This couples the decisions: a release high up does not just earn revenue
at that station, it also changes how much water — and how much room — the reservoir
below will have, hours later. A choice that looks best at one station in isolation can
therefore force a worse outcome further down.

---

### Inflow

Inflow is the natural water arriving in a reservoir from its own catchment — rain
running off the hillsides, and snow melting in spring. It is weather, not a choice, so
it is treated as a known input to the problem rather than something to be decided.
Inflow usually dwarfs the storage available to hold it: HJELLE receives about 92
million cubic metres over a year, against only 9 million cubic metres of active
storage. In other words the reservoir must turn over its entire contents roughly ten
times a year, so water cannot simply be held until the best moment.

---

### Head (Hbrutto and Hnetto)

Head is the height the water falls between the reservoir surface and the turbine, and
it is what actually produces the power — the same cubic metre is worth more from
higher up. Gross head, written Hbrutto, is the reservoir's average water surface
during the time step minus the elevation of the turbine; at SVOLETJONN this runs
between about 58 and 67 metres, at EASTER between about 115 and 215 metres. Net head,
written Hnetto, is gross head minus the head lost to friction on the way down, and it
is the net figure that determines production. Because head falls as the reservoir is
drawn down, emptying a reservoir makes every remaining cubic metre less valuable.

---

### Head loss

Head loss is the part of the drop that is wasted rubbing against the walls of the
tunnel between the reservoir and the turbine, instead of turning the machine. It grows
with the square of the flow: pushing twice as much water through the same tunnel
wastes four times as much head. At full discharge SVOLETJONN loses about 4.8 metres
and EASTER about 13.9 metres. This penalises running flat out — the last cubic metre
of a full-capacity release is worth noticeably less than the first.

---

### Turbine efficiency

Turbine efficiency is the share of the energy in the falling water that the machine
actually turns into electricity. It is not a constant: it climbs steeply from zero,
peaks over a band of flows, and falls away again at the top of the range. SVOLETJONN
reaches 93 % between roughly 2.8 and 3.5 cubic metres per second but drops to 88 % at
its maximum of 4.0, and SVEIGSHYL_II peaks at 91 % around 2.4 against a maximum of
6.0. Practically, every station has a sweet spot, and running either barely-on or
flat-out is wasteful.

---

### Action

An action is a single number between 0 and 1 that says how hard to run a unit in one
time step. Zero means the station is off and passes no water; one means full
discharge; anything between means partial operation, so an action of 0.5 at
SVOLETJONN passes 2.0 cubic metres per second. One action is set per generator per
time step, and a reservoir with an active hatch takes one action per time step as
well. The action is the only thing an operator actually chooses.

---

### Time step

A time step is one slice of the planning horizon, over which the action is held
constant and the water balance is settled. The horizon is cut into equal steps, and
the number of steps follows from the length of the price series. Hourly steps over a
year give 8760 steps; daily steps over the same year give 365. Shorter steps allow
finer control but multiply the number of decisions.

---

### Value function (V)

The value function is the single number that scores a complete plan, in euros. It has
two parts added together: the operating profit earned inside the horizon — energy
produced times the price at the time it was produced, less any operating costs — plus
the value of the water still sitting in the reservoirs when the horizon ends. The
second part is what stops the score from being short-sighted: water left in storage is
not wasted, it is simply electricity that has not been made yet, and a plan that ends
with full reservoirs has genuinely left the system better off than one that ends with
empty ones.

---

### Terminal water value

The terminal water value is the second half of the value function: a price put on
whatever water is left in active storage at the end of the horizon. Each cubic metre
is converted to energy using its station's fixed energy equivalent, and that energy is
valued at the rest price. Only water between LRW and HRW counts — anything above HRW
is treated as worth nothing, since it is about to spill. Without this term the best
plan would always be to empty every reservoir before the clock runs out, which is
obviously not how a real system is operated.

---

### Energy equivalent (LOCAL_ENERGY_EQUIVALENT)

The energy equivalent says how much electricity one cubic metre of water is worth at a
given station, given the head that station typically operates under. It is measured in
kilowatt-hours per cubic metre: SVOLETJONN's is 0.11, meaning a million cubic metres
is worth about 110 megawatt-hours, while SVEIGSHYL_II's is 0.39 because its water
falls further. It is a single fixed number per station, not recalculated as the
reservoir rises and falls. It is used only to value the water left over at the end of
the horizon — production during the horizon uses the actual head instead.

---

### Electricity price

The spot price is what one megawatt-hour of electricity sells for on the power
exchange, and it is the revenue side of every production decision. It changes from
hour to hour and from day to day, driven by demand, weather and the rest of the
market. In the uTAHPS daily series it averages about 138 euros per megawatt-hour but
ranges from almost nothing to 565 — a spread of four orders of magnitude, which is
precisely why timing releases is worth anything at all. The series is historical spot
data from the NO2 price region in southern Norway.

---

### Rest price (RESTPRICE)

The rest price is one number standing in for what water will be worth after the
planning horizon ends. It is expressed in the same units as the electricity price —
euros per megawatt-hour — and is the rate at which leftover water is converted into
value in the value function. It is chosen by the user before the run, not computed by
the simulator, and the uTAHPS datasets set it to 101. Setting it high makes storing
water attractive; setting it low encourages producing now.

---

### Overflow

Overflow is water escaping over the dam crest because the reservoir has risen above
its highest regulated level and there is nowhere else for it to go. It is not a choice
and cannot be switched off — once the level is above HRW, the more the level rises,
the faster water spills. Spilled water bypasses the turbines entirely, so it earns no
revenue, and it is not counted in the terminal water value either. Every cubic metre
that overflows is simply gone, which makes leaving enough empty space in a reservoir
ahead of large inflow a real part of the problem.

---

### rho

Rho is the ratio of the water a station will have to the water it could possibly pass:
rho = (initial active storage + total inflow) divided by (maximum discharge multiplied
by the length of one time step multiplied by the number of time steps). When rho is
greater than 1 there is more water arriving than the station can ever get rid of, so
the reservoir will overflow no matter what and the operator has no real choice but to
run continuously — timing barely matters. When rho is less than 1 water is scarce,
every cubic metre spent now is one not available later, and the whole problem becomes
choosing which hours to spend it in. HJELLE with SVOLETJONN sits at rho = 0.78: it
starts 70 % full with 6.3 million cubic metres of active water, receives 92.3 million
over the year, and the station can pass 126 million.

---

### R (storage ratio)

R is the ratio of storage to throughput: R = active storage divided by (maximum
discharge multiplied by the length of one time step multiplied by the number of time
steps). It answers how much of the horizon the reservoir could keep the station
running from storage alone — an R of 0.07 means about 7 % of the horizon, or roughly
26 days out of a year. A small R means the reservoir fills and empties quickly, so
water cannot be parked for long and releases must be timed precisely against the
price. HJELLE has R = 0.07 while GRESSE has R = 0.33, so GRESSE has almost five times
as much room to manoeuvre.

---

### uTAHPS

uTAHPS stands for the Upper Tovdalen Artificial Hydro Power System: a synthetic test
system, invented rather than surveyed, but built to the scale and structure of a real
Norwegian watercourse. It has four reservoirs and four power stations arranged as two
parallel branches that merge into a single reservoir before the sea.

Reservoirs, with LRW, HRW and active storage:

| Reservoir | LRW | HRW | Active storage |
|---|---|---|---|
| HJELLE | 748 m | 757 m | 9 Mm³ |
| GRESSE | 740 m | 749 m | 61 Mm³ |
| TOPPSY | 620 m | 650 m | 127 Mm³ |
| KROKNESVATN | 333 m | 433 m | 199 Mm³ |

Power stations, with the reservoir each draws from and its maximum discharge:

| Power station | Draws from | Maximum discharge |
|---|---|---|
| SVOLETJONN | HJELLE | 4.0 m³/s |
| SVEIGSHYL_I | TOPPSY | 5.9 m³/s |
| SVEIGSHYL_II | GRESSE | 6.0 m³/s |
| EASTER | KROKNESVATN | 9.8 m³/s |

SVOLETJONN releases HJELLE's water down to GRESSE; SVEIGSHYL_I and SVEIGSHYL_II
release TOPPSY's and GRESSE's water down to KROKNESVATN; and EASTER, the largest
station, releases KROKNESVATN's water to the sea.
