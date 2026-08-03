#include "logic.h"

#include <cmath>

namespace {

constexpr double kFullTurn = 360.0;
constexpr double kHalfTurn = 180.0;

// Positions closer than this count as identical.
constexpr double kEpsilon = 1e-9;

// Normalizes an angle to [0, 360).
double wrapTo360(double degrees) {
    const double wrapped = std::fmod(degrees, kFullTurn);
    return (wrapped < 0.0) ? wrapped + kFullTurn : wrapped;
}

// Signed shortest rotation from `from` to `to`, in (-180, +180].
double shortestDelta(double from, double to) {
    const double delta = wrapTo360(to - from);
    return (delta > kHalfTurn) ? delta - kFullTurn : delta;
}

// Speed for a move of `delta` degrees, clamped to the drive's limits.
double planSpeed(double delta, double timeToReach, double minSpeed, double maxSpeed,
                 bool& limited) {
    limited = false;

    // Already there: never lift a standing axis to minimum speed.
    if (std::abs(delta) <= kEpsilon) {
        return 0.0;
    }

    // A non-positive time budget would divide by zero; fall back to full speed.
    double speed = (timeToReach > 0.0) ? delta / timeToReach : std::copysign(maxSpeed, delta);

    if (maxSpeed > 0.0 && std::abs(speed) > maxSpeed) {
        speed = std::copysign(maxSpeed, speed);
        limited = true;
    } else if (minSpeed > 0.0 && std::abs(speed) < minSpeed) {
        speed = std::copysign(minSpeed, speed);
        limited = true;
    }
    return speed;
}

// Advances `pos` towards `target` by one cycle. Returns true once it arrived.
// `wrap` = true for the endlessly turning azimuth axis, false for elevation,
// which must not roll over 0/360 and turn through its end stops.
bool stepAxis(double& pos, double target, double& speed, double dt, bool wrap) {
    const double remaining = wrap ? shortestDelta(pos, target) : target - pos;

    if (std::abs(remaining) <= kEpsilon) {
        pos = target;
        speed = 0.0;
        return true;
    }

    // A non-positive cycle time must not drive the axis backwards.
    if (!(dt > 0.0)) {
        return false;
    }

    const double step = speed * dt;

    // This step would reach or overshoot the target: land exactly on it.
    if (std::abs(remaining) <= std::abs(step)) {
        pos = target;
        speed = 0.0;
        return true;
    }

    // Standstill: hold position.
    if (std::abs(step) <= kEpsilon) {
        return false;
    }

    pos = wrap ? wrapTo360(pos + step) : pos + step;
    return false;
}

}  // namespace

void logic::setNewAzimuthPosition() {
    updateInputs();
    _azPosReached = false;
    _motorSpeedAzimuth = planSpeed(shortestDelta(_azimuthPosition, _newAzimuthPosition),
                                   _timeToReachDemandedPos, _minMotorSpeed, _maxMotorSpeed,
                                   _azMotorSpeedLimited);
}

void logic::setNewElevationPosition() {
    updateInputs();
    _elPosReached = false;
    _motorSpeedElevation = planSpeed(_newElevationPosition - _elevationPosition,
                                     _timeToReachDemandedPos, _minMotorSpeed, _maxMotorSpeed,
                                     _elMotorSpeedLimited);
}

void logic::positionControl() {
    updateInputs();

    if (!_azPosReached) {
        _azPosReached =
            stepAxis(_azimuthPosition, _newAzimuthPosition, _motorSpeedAzimuth, _dt, true);
    }
    if (!_elPosReached) {
        _elPosReached =
            stepAxis(_elevationPosition, _newElevationPosition, _motorSpeedElevation, _dt, false);
    }

    // Once per cycle, not once per axis.
    propagateOutputs();
}
