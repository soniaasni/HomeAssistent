// Self-contained regression tests. No framework needed: build and run.
#include <cmath>
#include <cstdio>
#include <string>

#include "motion/angle_math.h"
#include "motion/axis_controller.h"
#include "motion/logic.h"

namespace {

int g_failures = 0;

void check(bool condition, const std::string& what) {
    if (!condition) {
        ++g_failures;
        std::printf("FAIL: %s\n", what.c_str());
    }
}

void checkNear(double actual, double expected, const std::string& what, double tol = 1e-9) {
    if (std::abs(actual - expected) > tol) {
        ++g_failures;
        std::printf("FAIL: %s (got %.12g, expected %.12g)\n", what.c_str(), actual, expected);
    }
}

motion::AxisConfig azimuthConfig() {
    motion::AxisConfig cfg;
    cfg.minSpeed = 0.5;
    cfg.maxSpeed = 10.0;
    cfg.timeToReachDemandedPos = 4.0;
    cfg.wrapAround = true;
    return cfg;
}

void testAngleMath() {
    checkNear(motion::wrapTo360(370.0), 10.0, "wrapTo360 above range");
    checkNear(motion::wrapTo360(-10.0), 350.0, "wrapTo360 below range");
    checkNear(motion::wrapTo360(-730.0), 350.0, "wrapTo360 multiple turns");
    checkNear(motion::wrapTo180(190.0), -170.0, "wrapTo180 above half turn");
    checkNear(motion::wrapTo180(-190.0), 170.0, "wrapTo180 below half turn");

    // The short way from 350 to 10 is +20, not -340.
    checkNear(motion::shortestDelta(350.0, 10.0), 20.0, "shortestDelta across the 0 seam");
    checkNear(motion::shortestDelta(10.0, 350.0), -20.0, "shortestDelta backwards across the seam");
    checkNear(motion::shortestDelta(0.0, 180.0), 180.0, "shortestDelta half turn is deterministic");
}

void testReachesTargetAndSetsFlag() {
    motion::AxisController axis(azimuthConfig());
    axis.setPosition(0.0);
    axis.setDemandedPosition(20.0);

    check(!axis.positionReached(), "axis is not reached right after a new target");
    checkNear(axis.speed(), 5.0, "speed is delta / time budget");

    for (int i = 0; i < 100 && !axis.positionReached(); ++i) {
        axis.update(0.1);
    }

    // The original never assigned _azPosReached / _elPosReached, so this flag
    // could never become true.
    check(axis.positionReached(), "axis reports the target as reached");
    checkNear(axis.position(), 20.0, "axis lands exactly on the target");
    checkNear(axis.speed(), 0.0, "axis stops once it has arrived");
}

void testTakesShortWayAcrossSeam() {
    motion::AxisConfig cfg = azimuthConfig();
    cfg.timeToReachDemandedPos = 2.0;
    motion::AxisController axis(cfg);
    axis.setPosition(350.0);
    axis.setDemandedPosition(10.0);

    check(axis.speed() > 0.0, "moves clockwise through 0 instead of the long way round");

    axis.update(1.0);
    checkNear(axis.position(), 0.0, "position wraps at 360 rather than running to 360+");

    for (int i = 0; i < 100 && !axis.positionReached(); ++i) {
        axis.update(0.1);
    }
    checkNear(axis.position(), 10.0, "arrives at the target after the wrap");
}

void testSpeedClamping() {
    motion::AxisConfig cfg = azimuthConfig();
    cfg.timeToReachDemandedPos = 1.0;
    motion::AxisController fast(cfg);
    fast.setPosition(0.0);
    fast.setDemandedPosition(170.0);
    checkNear(fast.speed(), 10.0, "speed is clamped to maxSpeed");
    check(fast.speedLimited(), "the limited flag is raised on the upper clamp");

    motion::AxisController slow(cfg);
    slow.setPosition(0.0);
    slow.setDemandedPosition(-0.2);  // wraps to 359.8, delta -0.2
    checkNear(slow.speed(), -0.5, "speed is clamped to minSpeed with the sign kept");
    check(slow.speedLimited(), "the limited flag is raised on the lower clamp");

    // Sign preservation for a negative move that is too fast.
    motion::AxisController backwards(cfg);
    backwards.setPosition(170.0);
    backwards.setDemandedPosition(0.0);
    checkNear(backwards.speed(), -10.0, "negative direction survives the upper clamp");
}

void testNoHuntAtStandstill() {
    motion::AxisController axis(azimuthConfig());
    axis.setPosition(42.0);
    axis.setDemandedPosition(42.0);

    check(axis.positionReached(), "a target equal to the position counts as reached");
    checkNear(axis.speed(), 0.0, "minSpeed never lifts a zero speed off standstill");

    axis.update(1.0);
    checkNear(axis.position(), 42.0, "an axis at its target does not drift");
}

void testMinSpeedDoesNotOvershoot() {
    motion::AxisConfig cfg = azimuthConfig();
    cfg.minSpeed = 5.0;
    cfg.timeToReachDemandedPos = 10.0;
    motion::AxisController axis(cfg);
    axis.setPosition(0.0);
    axis.setDemandedPosition(0.5);  // nominal 0.05 deg/s, lifted to 5 deg/s

    checkNear(axis.speed(), 5.0, "minSpeed applies to a tiny move");
    axis.update(1.0);  // a full step would be 5 deg, the target is 0.5 deg away
    checkNear(axis.position(), 0.5, "the last step lands on the target instead of overshooting");
    check(axis.positionReached(), "the overshoot-guarded step also sets the reached flag");
}

void testElevationRespectsEndStops() {
    motion::AxisConfig cfg;
    cfg.maxSpeed = 10.0;
    cfg.timeToReachDemandedPos = 1.0;
    cfg.wrapAround = false;
    cfg.minPosition = 0.0;
    cfg.maxPosition = 90.0;

    motion::AxisController axis(cfg);
    axis.setPosition(10.0);
    axis.setDemandedPosition(120.0);  // beyond the end stop

    checkNear(axis.demandedPosition(), 90.0, "an out-of-range target is clamped to the end stop");
    check(axis.speed() > 0.0, "a non-wrapping axis moves up, it does not wrap the short way down");

    for (int i = 0; i < 200 && !axis.positionReached(); ++i) {
        axis.update(0.1);
    }
    checkNear(axis.position(), 90.0, "the axis stops at the end stop");

    motion::AxisController down(cfg);
    down.setPosition(10.0);
    down.setDemandedPosition(-20.0);
    checkNear(down.demandedPosition(), 0.0, "the lower end stop is honoured too");
    check(down.speed() < 0.0, "moving towards the lower end stop uses a negative speed");
}

void testInvalidConfigDoesNotDivideByZero() {
    motion::AxisConfig cfg;
    cfg.timeToReachDemandedPos = 0.0;
    cfg.maxSpeed = 6.0;
    check(!cfg.isValid(), "a zero move time is reported as invalid config");

    motion::AxisController axis(cfg);
    axis.setPosition(0.0);
    axis.setDemandedPosition(30.0);
    checkNear(axis.speed(), 6.0, "a zero move time falls back to maxSpeed instead of dividing by 0");
    check(std::isfinite(axis.speed()), "speed stays finite");

    motion::AxisConfig unusable;
    unusable.timeToReachDemandedPos = 0.0;
    unusable.maxSpeed = 0.0;
    motion::AxisController stuck(unusable);
    stuck.setPosition(0.0);
    stuck.setDemandedPosition(30.0);
    stuck.update(1.0);
    check(stuck.configInvalid(), "an unusable config is flagged");
    checkNear(stuck.position(), 0.0, "an unusable config holds position instead of snapping");
}

void testZeroTimestepIsANoOp() {
    motion::AxisController axis(azimuthConfig());
    axis.setPosition(0.0);
    axis.setDemandedPosition(20.0);
    axis.update(0.0);
    checkNear(axis.position(), 0.0, "dt = 0 does not move the axis");
    axis.update(-1.0);
    checkNear(axis.position(), 0.0, "a negative dt does not move the axis backwards");
}

/// Drives the public `logic` API through a full move and counts the I/O calls.
class TestLogic : public logic {
public:
    TestLogic(double azTarget, double elTarget, double dt)
        : _azTarget(azTarget), _elTarget(elTarget), _cycle(dt) {
        motion::AxisConfig az;
        az.maxSpeed = 10.0;
        az.timeToReachDemandedPos = 2.0;
        az.wrapAround = true;
        _azimuth.setConfig(az);

        motion::AxisConfig el;
        el.maxSpeed = 10.0;
        el.timeToReachDemandedPos = 2.0;
        el.wrapAround = false;
        el.minPosition = 0.0;
        el.maxPosition = 90.0;
        _elevation.setConfig(el);
    }

    int outputCycles() const { return _outputs; }

protected:
    void updateInputs() override {
        _newAzimuthPosition = _azTarget;
        _newElevationPosition = _elTarget;
        _dt = _cycle;
    }

    void propagateOutputs() override { ++_outputs; }

private:
    double _azTarget;
    double _elTarget;
    double _cycle;
    int _outputs = 0;
};

void testLogicEndToEnd() {
    TestLogic ctrl(90.0, 45.0, 0.1);
    ctrl.setNewAzimuthPosition();
    ctrl.setNewElevationPosition();

    int cycles = 0;
    while (!ctrl.allAxesReached() && cycles < 1000) {
        ctrl.positionControl();
        ++cycles;
    }

    check(ctrl.allAxesReached(), "both axes reach their targets");
    checkNear(ctrl.azimuthPosition(), 90.0, "azimuth lands on its target");
    checkNear(ctrl.elevationPosition(), 45.0, "elevation lands on its target");
    check(ctrl.outputCycles() == cycles, "outputs are published exactly once per cycle");
}

}  // namespace

int main() {
    testAngleMath();
    testReachesTargetAndSetsFlag();
    testTakesShortWayAcrossSeam();
    testSpeedClamping();
    testNoHuntAtStandstill();
    testMinSpeedDoesNotOvershoot();
    testElevationRespectsEndStops();
    testInvalidConfigDoesNotDivideByZero();
    testZeroTimestepIsANoOp();
    testLogicEndToEnd();

    if (g_failures == 0) {
        std::printf("all motion_control tests passed\n");
        return 0;
    }
    std::printf("%d check(s) failed\n", g_failures);
    return 1;
}
