#!/usr/bin/env python
"""
Exact Python port of HERSS's ArrayCurve (src/arraycurve.cpp), the piecewise-
linear curve lookup used for every reservoir, overflow and turbine curve.

Why this exists. ArrayCurve is NOT plain piecewise-linear interpolation. It
normalizes both axes to [0,1], then precomputes a POINTS_IN_ARRAY=1000 bucket
table mapping each bucket to a curve segment (initializeArrays, :68-84). At
lookup time it picks the bucket by `idx = int(frac*1000)` and evaluates THAT
bucket's segment line (:181-203). Inside a segment this is exact; but within
one bucket width of a breakpoint the bucket can still be assigned to the
previous segment, and the lookup then EXTRAPOLATES the previous segment's line
past the breakpoint.

Using np.interp instead leaves a small residual that accumulates over a 365-step
horizon: on hjelle_daily it reached ~0.74 EUR of a ~1.5 MEUR value function.
That is tiny, but it is a systematic model discrepancy, not float noise, and
leaving it in would mean every later "replica vs HERSS" difference has to be
argued about instead of read off. Porting the bucket table removes the whole
question: the replica becomes exact to floating point.

Cited line numbers are src/arraycurve.cpp at upstream commit 029a2d5
(HERSS VERSION 3.1.03 / VERSION_DATE 20260611).
"""

import numpy as np

POINTS_IN_ARRAY = 1000  # arraycurve.h:36


class ArrayCurve:
    def __init__(self, x_points, y_points):
        x = np.asarray(x_points, dtype=float).copy()
        y = np.asarray(y_points, dtype=float).copy()
        if len(x) != len(y):
            raise ValueError("x_points and y_points must have equal length")
        self.nr_pts = len(x)

        # initializeArrays :42-67 -- min/max over the RAW points, then normalize
        self.xmin, self.xmax = float(x.min()), float(x.max())
        self.ymin, self.ymax = float(y.min()), float(y.max())
        self.xn = (x - self.xmin) / (self.xmax - self.xmin)
        self.yn = (y - self.ymin) / (self.ymax - self.ymin)

        # initializeArrays :69-84 -- bucket table over the normalized x range
        n = POINTS_IN_ARRAY
        self.xlower = np.empty(n)
        self.xupper = np.empty(n)
        self.ylower = np.empty(n)
        self.yupper = np.empty(n)

        self.xlower[0], self.ylower[0] = self.xn[0], self.yn[0]
        self.xupper[0], self.yupper[0] = self.xn[1], self.yn[1]

        dx = (self.xn[-1] - self.xn[0]) / float(n)
        idx_points = 0
        for t in range(1, n):
            xt = self.xn[0] + t * dx
            # NB: advances by at most one segment per bucket, exactly as in C++.
            if xt >= self.xn[idx_points + 1]:
                idx_points += 1
            self.xlower[t] = self.xn[idx_points]
            self.ylower[t] = self.yn[idx_points]
            self.xupper[t] = self.xn[idx_points + 1]
            self.yupper[t] = self.yn[idx_points + 1]

        self._slope = ((self.yupper - self.ylower) / (self.xupper - self.xlower))

        # Plain-Python copies of the lookup tables. The scalar path is called
        # ~1500 times per full-horizon replica run and tens of millions of times
        # across a baseline sweep; going through numpy for a single float costs
        # ~10 us, against ~0.6 us for list indexing. Same arithmetic either way.
        self._xl = self.xlower.tolist()
        self._yl = self.ylower.tolist()
        self._sl = self._slope.tolist()
        self._x0 = float(self.xn[0])
        self._xspan = float(self.xn[-1] - self.xn[0])
        self._xr = self.xmax - self.xmin
        self._yr = self.ymax - self.ymin

    def x2y_scalar(self, x):
        """Scalar fast path. Identical arithmetic to x2y, no numpy dispatch."""
        xt = (x - self.xmin) / self._xr
        frac = (xt - self._x0) / self._xspan
        if frac < 0.0:
            frac = 0.0
        elif frac > 1.0:
            frac = 1.0
        idx = int(frac * POINTS_IN_ARRAY)
        if idx >= POINTS_IN_ARRAY:
            idx = POINTS_IN_ARRAY - 1
        return (self._sl[idx] * (xt - self._xl[idx]) + self._yl[idx]) * self._yr + self.ymin

    def x2y(self, x):
        """Vectorized x2y (:120-221). Accepts scalars or arrays; returns float or ndarray."""
        if type(x) is float or type(x) is int:
            return self.x2y_scalar(x)
        scalar = np.isscalar(x) or (isinstance(x, np.ndarray) and x.ndim == 0)
        xa = np.asarray(x, dtype=float)

        xt = (xa - self.xmin) / (self.xmax - self.xmin)          # :152

        # :180-186
        frac = (xt - self.xn[0]) / (self.xn[-1] - self.xn[0])
        frac = np.clip(frac, 0.0, 1.0)
        idx = (frac * float(POINTS_IN_ARRAY)).astype(np.int64)
        idx = np.clip(idx, 0, POINTS_IN_ARRAY - 1)

        # :202-206
        y = self._slope[idx] * (xt - self.xlower[idx]) + self.ylower[idx]
        y = y * (self.ymax - self.ymin) + self.ymin

        return float(y) if scalar else y
