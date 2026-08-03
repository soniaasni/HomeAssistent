#include "motion/logic.h"

void logic::setNewAzimuthPosition() {
    updateInputs();
    _azimuth.setDemandedPosition(_newAzimuthPosition);
}

void logic::setNewElevationPosition() {
    updateInputs();
    _elevation.setDemandedPosition(_newElevationPosition);
}

void logic::positionControl() {
    updateInputs();

    _azimuth.update(_dt);
    _elevation.update(_dt);

    // Once per cycle. The original called propagateOutputs() inside each of
    // the two axis blocks, so outputs were published twice per cycle while
    // both axes were moving and not at all once both had arrived.
    propagateOutputs();
}
