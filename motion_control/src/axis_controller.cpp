#include "motion/axis_controller.h"

#include "motion/angle_math.h"

namespace motion {
namespace {

/// Speeds below this magnitude are treated as standstill. Comparing a double
/// against exact 0 (as the original `fabs(...) > 0` guards did) is not a
/// meaningful test for "the drive is moving".
constexpr double kSpeedEpsilon = 1e-9;

/// Positions closer than this are considered identical, so a move that is
/// already at its target does not start a hunt at minimum speed.
constexpr double kPositionEpsilon = 1e-9;

}  // namespace

bool AxisConfig::isValid() const noexcept {
    if (minSpeed < 0.0 || maxSpeed < 0.0) {
        return false;
    }
    if (maxSpeed > 0.0 && minSpeed > maxSpeed) {
        return false;
    }
    if (!(timeToReachDemandedPos > 0.0)) {
        return false;
    }
    if (!wrapAround && !(minPosition < maxPosition)) {
        return false;
    }
    return true;
}

void AxisController::setConfig(const AxisConfig& config) noexcept {
    _config = config;
    _position = normalizePosition(_position);
    _demandedPosition = normalizePosition(_demandedPosition);
    if (!_positionReached) {
        computeSpeed();
    }
}

void AxisController::setPosition(double degrees) noexcept {
    // Encoder feedback. It does not re-plan the move: like the original
    // `_calcMotorSpeed` flag, the commanded rate stays constant until a new
    // target is set. Call setDemandedPosition() again to re-plan.
    _position = normalizePosition(degrees);
    if (std::abs(remainingDelta()) <= kPositionEpsilon) {
        _positionReached = true;
        _speed = 0.0;
    }
}

void AxisController::setDemandedPosition(double degrees) noexcept {
    _demandedPosition = normalizePosition(degrees);
    _speedLimited = false;
    _configInvalid = false;
    _positionReached = std::abs(remainingDelta()) <= kPositionEpsilon;
    if (_positionReached) {
        _speed = 0.0;
        return;
    }
    computeSpeed();
}

double AxisController::normalizePosition(double degrees) const noexcept {
    return _config.wrapAround ? wrapTo360(degrees)
                              : clampTo(degrees, _config.minPosition, _config.maxPosition);
}

double AxisController::remainingDelta() const noexcept {
    // For a wrapping axis this single value replaces both of the original
    // distance expressions: |shortestDelta| already is min(|d|, 360 - |d|).
    return _config.wrapAround ? shortestDelta(_position, _demandedPosition)
                              : _demandedPosition - _position;
}

void AxisController::computeSpeed() noexcept {
    const double delta = remainingDelta();

    if (std::abs(delta) <= kPositionEpsilon) {
        _speed = 0.0;
        _speedLimited = false;
        return;
    }

    double speed = 0.0;
    if (_config.timeToReachDemandedPos > 0.0) {
        speed = delta / _config.timeToReachDemandedPos;
    } else if (_config.maxSpeed > 0.0) {
        // Guards the division by zero the original code performed unchecked.
        speed = std::copysign(_config.maxSpeed, delta);
    } else {
        _configInvalid = true;
        _speed = 0.0;
        _speedLimited = false;
        return;
    }

    _configInvalid = false;
    _speedLimited = false;

    const double magnitude = std::abs(speed);
    if (_config.maxSpeed > 0.0 && magnitude > _config.maxSpeed) {
        speed = std::copysign(_config.maxSpeed, speed);
        _speedLimited = true;
    } else if (_config.minSpeed > 0.0 && magnitude < _config.minSpeed) {
        speed = std::copysign(_config.minSpeed, speed);
        _speedLimited = true;
    }

    _speed = speed;
}

void AxisController::update(double dt) noexcept {
    if (_positionReached || !(dt > 0.0)) {
        return;
    }

    const double remaining = remainingDelta();
    if (std::abs(remaining) <= kPositionEpsilon) {
        _position = _demandedPosition;
        _speed = 0.0;
        _positionReached = true;
        return;
    }

    if (std::abs(_speed) <= kSpeedEpsilon) {
        // Misconfigured or commanded to standstill: hold position instead of
        // snapping to the target.
        return;
    }

    const double step = _speed * dt;

    // Last step: the move would reach or overshoot the target within this
    // cycle, so land exactly on it. The original code never set the
    // "position reached" flag here, so the axis kept re-entering the control
    // block forever.
    if (std::abs(remaining) <= std::abs(step)) {
        _position = _demandedPosition;
        _speed = 0.0;
        _positionReached = true;
        return;
    }

    _position = normalizePosition(_position + step);

    if (!_config.wrapAround &&
        (_position <= _config.minPosition || _position >= _config.maxPosition)) {
        // Ran into an end stop before reaching the target.
        _speed = 0.0;
        _positionReached = std::abs(remainingDelta()) <= kPositionEpsilon;
    }
}

}  // namespace motion
