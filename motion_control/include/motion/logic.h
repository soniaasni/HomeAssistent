#pragma once

#include "motion/axis_controller.h"

/// Positioning logic for a two-axis (azimuth / elevation) rotator.
///
/// The public entry points keep the names and signatures of the original
/// implementation so existing call sites do not have to change. Everything
/// below them now runs through a single, shared axis controller.
class logic {
public:
    logic() = default;
    virtual ~logic() = default;

    /// Applies the azimuth target that updateInputs() delivered.
    void setNewAzimuthPosition();

    /// Applies the elevation target that updateInputs() delivered.
    void setNewElevationPosition();

    /// One control cycle for both axes.
    void positionControl();

    [[nodiscard]] double azimuthPosition() const noexcept { return _azimuth.position(); }
    [[nodiscard]] double elevationPosition() const noexcept { return _elevation.position(); }
    [[nodiscard]] double motorSpeedAzimuth() const noexcept { return _azimuth.speed(); }
    [[nodiscard]] double motorSpeedElevation() const noexcept { return _elevation.speed(); }
    [[nodiscard]] bool azPosReached() const noexcept { return _azimuth.positionReached(); }
    [[nodiscard]] bool elPosReached() const noexcept { return _elevation.positionReached(); }
    [[nodiscard]] bool azMotorSpeedLimited() const noexcept { return _azimuth.speedLimited(); }
    [[nodiscard]] bool elMotorSpeedLimited() const noexcept { return _elevation.speedLimited(); }

    /// True while both axes sit on their target — the condition the caller
    /// previously had to reconstruct from two separate flags.
    [[nodiscard]] bool allAxesReached() const noexcept {
        return _azimuth.positionReached() && _elevation.positionReached();
    }

protected:
    /// Reads the demanded positions, the cycle time and the speed limits from
    /// the I/O layer. Hook your existing implementation in here; the base
    /// version deliberately does nothing.
    virtual void updateInputs() {}

    /// Publishes positions, speeds and status flags to the I/O layer. Hook
    /// your existing implementation in here.
    virtual void propagateOutputs() {}

    // Inputs, written by updateInputs().
    double _newAzimuthPosition = 0.0;
    double _newElevationPosition = 0.0;
    double _dt = 0.0;

    // Azimuth turns endlessly, elevation has mechanical end stops. Set the
    // real travel range of your hardware here — the original code wrapped
    // elevation modulo 360 too, which lets the mast swing through its stops.
    motion::AxisController _azimuth{motion::AxisConfig{/*minSpeed=*/0.0,
                                                       /*maxSpeed=*/0.0,
                                                       /*timeToReachDemandedPos=*/1.0,
                                                       /*wrapAround=*/true}};
    motion::AxisController _elevation{motion::AxisConfig{/*minSpeed=*/0.0,
                                                         /*maxSpeed=*/0.0,
                                                         /*timeToReachDemandedPos=*/1.0,
                                                         /*wrapAround=*/false,
                                                         /*minPosition=*/0.0,
                                                         /*maxPosition=*/90.0}};
};
