#pragma once

namespace motion {

/// Static configuration of one rotational axis.
struct AxisConfig {
    /// Magnitude of the smallest speed the drive can actually hold, in deg/s.
    /// 0 disables the lower clamp.
    double minSpeed = 0.0;

    /// Magnitude of the highest permitted speed, in deg/s. 0 disables the
    /// upper clamp.
    double maxSpeed = 0.0;

    /// Nominal time budget for a move, in seconds. Must be > 0.
    double timeToReachDemandedPos = 1.0;

    /// True for an endlessly rotating axis (azimuth): positions wrap at 360
    /// and the controller always takes the shorter way round.
    /// False for an axis with mechanical end stops (elevation): positions are
    /// clamped to [minPosition, maxPosition] and never wrap.
    bool wrapAround = true;

    /// Mechanical travel range, only used when wrapAround == false.
    double minPosition = 0.0;
    double maxPosition = 360.0;

    [[nodiscard]] bool isValid() const noexcept;
};

/// Constant-rate point-to-point controller for a single rotational axis.
///
/// One instance replaces the azimuth block and the elevation block of the
/// original `logic::positionControl()`, which were literal copies of each
/// other apart from the member names.
class AxisController {
public:
    AxisController() = default;
    explicit AxisController(const AxisConfig& config) noexcept : _config(config) {}

    void setConfig(const AxisConfig& config) noexcept;
    [[nodiscard]] const AxisConfig& config() const noexcept { return _config; }

    /// Feeds back the measured position, e.g. from an encoder. This does not
    /// re-plan the running move: the commanded rate stays constant until a
    /// new target is set.
    void setPosition(double degrees) noexcept;

    /// Requests a new target. Re-arms speed calculation and clears the
    /// "reached" and "speed limited" flags, exactly like the original
    /// setNewAzimuthPosition()/setNewElevationPosition() pair did.
    void setDemandedPosition(double degrees) noexcept;

    /// Advances the axis by one control cycle of `dt` seconds.
    void update(double dt) noexcept;

    [[nodiscard]] double position() const noexcept { return _position; }
    [[nodiscard]] double demandedPosition() const noexcept { return _demandedPosition; }
    [[nodiscard]] double speed() const noexcept { return _speed; }
    [[nodiscard]] bool positionReached() const noexcept { return _positionReached; }
    [[nodiscard]] bool speedLimited() const noexcept { return _speedLimited; }

    /// True when the axis cannot move because the configuration is unusable
    /// (non-positive move time and no maximum speed to fall back on).
    [[nodiscard]] bool configInvalid() const noexcept { return _configInvalid; }

private:
    /// Signed shortest distance to the target, honouring wrapAround.
    [[nodiscard]] double remainingDelta() const noexcept;
    [[nodiscard]] double normalizePosition(double degrees) const noexcept;
    void computeSpeed() noexcept;

    AxisConfig _config{};
    double _position = 0.0;
    double _demandedPosition = 0.0;
    double _speed = 0.0;
    bool _positionReached = true;
    bool _speedLimited = false;
    bool _configInvalid = false;
};

}  // namespace motion
