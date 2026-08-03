#pragma once

#include <cmath>

namespace motion {

inline constexpr double kFullTurn = 360.0;
inline constexpr double kHalfTurn = 180.0;

/// Normalizes an angle to [0, 360).
[[nodiscard]] inline double wrapTo360(double degrees) noexcept {
    double wrapped = std::fmod(degrees, kFullTurn);
    if (wrapped < 0.0) {
        wrapped += kFullTurn;
    }
    return wrapped;
}

/// Normalizes an angle to (-180, +180].
///
/// The original code did this with a three-branch if/else-if chain that only
/// worked for inputs already inside (-360, +360). fmod-based wrapping is
/// correct for arbitrary inputs and has no unhandled branch.
[[nodiscard]] inline double wrapTo180(double degrees) noexcept {
    const double wrapped = wrapTo360(degrees);
    return (wrapped > kHalfTurn) ? wrapped - kFullTurn : wrapped;
}

/// Signed shortest rotation from `from` to `to`, in (-180, +180].
///
/// A half-turn is reported as +180 (clockwise) so the direction is
/// deterministic; the original chain resolved that tie to -180.
[[nodiscard]] inline double shortestDelta(double from, double to) noexcept {
    return wrapTo180(to - from);
}

/// Clamps to [low, high]. std::clamp would need <algorithm> and a reference
/// dance; this keeps the header free of surprises for freestanding targets.
[[nodiscard]] inline double clampTo(double value, double low, double high) noexcept {
    if (value < low) {
        return low;
    }
    return (value > high) ? high : value;
}

}  // namespace motion
