"""Small depth-gesture state machines used by overhead desk mode."""


class DepthTapDetector:
    """Fire once after a finger leaves its learned rest plane and returns."""

    def __init__(self, trigger=0.14, release=0.055, cooldown=0.22,
                 baseline_alpha=0.04):
        if not 0 < release < trigger:
            raise ValueError("release must be smaller than trigger")
        self.trigger = float(trigger)
        self.release = float(release)
        self.cooldown = float(cooldown)
        self.baseline_alpha = float(baseline_alpha)
        self.reset()

    def reset(self):
        self.baseline = None
        self.armed = False
        self.last_fire = float("-inf")

    def update(self, value, now):
        value = float(value)
        now = float(now)
        if self.baseline is None:
            self.baseline = value
            return False

        deviation = abs(value - self.baseline)
        if self.armed:
            if deviation <= self.release:
                self.armed = False
                self.baseline += self.baseline_alpha * (value - self.baseline)
                if now - self.last_fire >= self.cooldown:
                    self.last_fire = now
                    return True
            return False

        if deviation >= self.trigger:
            self.armed = True
            return False

        self.baseline += self.baseline_alpha * (value - self.baseline)
        return False


class DepthHoldDetector:
    """Hold while a finger is lifted away from its learned rest plane."""

    def __init__(self, trigger=0.16, release=0.065, baseline_alpha=0.04):
        if not 0 < release < trigger:
            raise ValueError("release must be smaller than trigger")
        self.trigger = float(trigger)
        self.release = float(release)
        self.baseline_alpha = float(baseline_alpha)
        self.reset()

    def reset(self):
        self.baseline = None
        self.active = False

    def update(self, value):
        value = float(value)
        if self.baseline is None:
            self.baseline = value
            return False, False

        deviation = abs(value - self.baseline)
        changed = False
        if self.active:
            if deviation <= self.release:
                self.active = False
                changed = True
                self.baseline += self.baseline_alpha * (value - self.baseline)
        else:
            if deviation >= self.trigger:
                self.active = True
                changed = True
            else:
                self.baseline += self.baseline_alpha * (value - self.baseline)

        return self.active, changed


class FourFingerScrollDetector:
    """Detect coherent vertical motion of four resting non-thumb fingers.

    The gesture deliberately ignores the thumb. Four per-finger depth baselines
    decide whether index/middle/ring/pinky are still on their learned desk
    plane; coherent vertical XY motion then enters scrolling. Horizontal motion
    and single-finger movement do not activate it.
    """

    def __init__(self, rest_threshold=0.085, start_delta=0.006, speed=95.0,
                 release_timeout=0.16, coherence=0.008, axis_ratio=1.25,
                 baseline_alpha=0.025, settle_frames=4, invert=False):
        self.rest_threshold = float(rest_threshold)
        self.start_delta = float(start_delta)
        self.speed = float(speed)
        self.release_timeout = float(release_timeout)
        self.coherence = float(coherence)
        self.axis_ratio = float(axis_ratio)
        self.baseline_alpha = float(baseline_alpha)
        self.settle_frames = int(settle_frames)
        self.invert = bool(invert)
        if self.rest_threshold <= 0 or self.start_delta <= 0:
            raise ValueError("scroll thresholds must be positive")
        if self.speed <= 0 or self.release_timeout <= 0:
            raise ValueError("scroll speed/release must be positive")
        if self.settle_frames < 1:
            raise ValueError("settle_frames must be >= 1")
        self.reset()

    @staticmethod
    def _median(values):
        values = sorted(float(v) for v in values)
        n = len(values)
        mid = n // 2
        if n % 2:
            return values[mid]
        return (values[mid - 1] + values[mid]) / 2.0

    def reset(self):
        self.baselines = None
        self.prev_points = None
        self.active = False
        self.last_motion = float("-inf")
        self.accumulator = 0.0
        self.settled = 0

    def _update_baselines(self, depths):
        if self.baselines is None:
            self.baselines = [float(v) for v in depths]
            return
        a = self.baseline_alpha
        self.baselines = [
            base + a * (float(value) - base)
            for base, value in zip(self.baselines, depths)
        ]

    def update(self, points, depths, now):
        if len(points) != 4 or len(depths) != 4:
            raise ValueError("four-finger scroll requires exactly four fingers")
        points = [(float(x), float(y)) for x, y in points]
        depths = [float(v) for v in depths]
        now = float(now)

        if self.baselines is None:
            self._update_baselines(depths)
            self.prev_points = points
            self.settled = 1
            return False, 0

        deviations = [
            abs(value - base)
            for value, base in zip(depths, self.baselines)
        ]
        resting = max(deviations) <= self.rest_threshold

        if self.prev_points is None:
            self.prev_points = points
            return False, 0

        dx = [p[0] - old[0] for p, old in zip(points, self.prev_points)]
        dy = [p[1] - old[1] for p, old in zip(points, self.prev_points)]
        self.prev_points = points

        mdx = self._median(dx)
        mdy = self._median(dy)
        coherent = max(abs(v - mdy) for v in dy) <= self.coherence
        vertical = abs(mdy) >= self.axis_ratio * abs(mdx)
        activation_motion = abs(mdy) >= self.start_delta and vertical and coherent
        continuation_motion = (
            abs(mdy) >= self.start_delta * 0.20 and vertical and coherent
        )

        if not resting:
            self.active = False
            self.accumulator = 0.0
            self.settled = 0
            return False, 0

        if not self.active:
            self._update_baselines(depths)
            self.settled += 1
            if self.settled >= self.settle_frames and activation_motion:
                self.active = True
                self.last_motion = now
            else:
                return False, 0
        elif continuation_motion:
            self.last_motion = now
        elif now - self.last_motion > self.release_timeout:
            self.active = False
            self.accumulator = 0.0
            self._update_baselines(depths)
            return False, 0

        if continuation_motion or activation_motion:
            direction = 1.0 if self.invert else -1.0
            self.accumulator += direction * mdy * self.speed

        steps = int(self.accumulator)
        if steps:
            self.accumulator -= steps
        return self.active, steps
