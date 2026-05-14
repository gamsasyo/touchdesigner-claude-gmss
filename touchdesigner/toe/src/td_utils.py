"""TouchDesigner Utility Functions.

These functions are designed to be imported and bound to TouchDesignerAPI class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from typing import TypeAlias
    OP: TypeAlias = Any  # TouchDesigner operator type


class AABB(NamedTuple):
    """Axis-Aligned Bounding Box."""
    min_x: int
    min_y: int
    max_x: int
    max_y: int

    @property
    def width(self) -> int:
        return self.max_x - self.min_x

    @property
    def height(self) -> int:
        return self.max_y - self.min_y

    @property
    def x(self) -> int:
        return self.min_x

    @property
    def y(self) -> int:
        return self.min_y


__all__ = [
    'AABB',
    'MoveOp', 'CreateOp', 'CreateGeometryComp', 'ChainOperators',
    'GetOperatorInfo', 'GetParameterList', 'GetParameterHelp',
    'PrintLayout', 'CheckErrors',
    # Layout utilities
    'GetBounds', 'CheckOverlap', 'GetAllBounds',
    'FindEmptyArea', 'FindTypeConversionPosition',
    # Layout-rule helpers (gmss fork)
    'AlignReferenceUnderGeo', 'AlignInstanceChainWithGeo',
    'LayoutGeoGroup', 'VerifyNoOverlaps',
]


# =============================================================================
# Layout constants (gmss layout convention)
# See skills/td-guide/reference/layout-rules.md for the full convention.
# =============================================================================

LAYOUT_X_SPACING = 250        # X spacing within a chain
LAYOUT_Y_FAMILY = 175         # Y spacing between rows of the same group
LAYOUT_Y_GROUP = 300          # Y spacing between separate logical groups
LAYOUT_GEO_Y_OFFSET = 20      # Geo COMP sits slightly below its instance row
                              # (accounts for COMP's taller visual size)


def MoveOp(self, target: OP | str, x: int, y: int) -> OP:
    """Move operator to specified position with docked operators.

    Args:
        target: Operator or path string
        x: Target X position
        y: Target Y position

    Returns:
        OP: The moved operator
    """
    if isinstance(target, str):
        target = op(target)

    # Calculate offset
    dx = x - target.nodeX
    dy = y - target.nodeY

    # Move docked operators first (maintain relative position)
    for d in target.docked:
        d.nodeX += dx
        d.nodeY += dy

    # Move the operator itself
    target.nodeX = x
    target.nodeY = y

    return target


def CreateOp(self, base: OP | str, op_type: type, name: str, x: int | None = None, y: int | None = None) -> OP:
    """Create operator with viewer enabled and proper positioning.

    Args:
        base: Parent operator
        op_type: Operator type (e.g., boxSOP, nullCHOP, glslTOP)
        name: Operator name (auto-incremented if duplicate exists)
        x: X position (optional)
        y: Y position (optional)

    Returns:
        OP: Created operator

    Note:
        If an operator with the same name exists, TD auto-increments
        the name (e.g., null1 -> null2). The actual created operator
        is returned, so check its name if needed.
    """
    if isinstance(base, str):
        base = op(base)

    new_op = base.create(op_type, name)
    new_op.viewer = True

    # Move to position if specified (handles docked operators)
    if x is not None and y is not None:
        MoveOp(self, new_op, x, y)

    return new_op


def CreateGeometryComp(
    self,
    base: OP | str,
    name: str,
    input_op: OP | None = None,
    x: int | None = None,
    y: int | None = None,
) -> tuple[OP, OP, OP]:
    """Create Geometry COMP with In/Out setup.

    Args:
        base: Parent operator
        name: COMP name
        input_op: Optional SOP/POP to connect (auto-detects family)
        x: X position (optional)
        y: Y position (optional)

    Returns:
        tuple: (geo, in_op, out_op)
    """
    if isinstance(base, str):
        base = op(base)

    # Detect family from input_op
    family = 'SOP'
    if input_op is not None:
        family = input_op.family

    # Create Geometry COMP
    geo = CreateOp(self, base, geometryCOMP, name, x, y)

    # Remove default torus
    for child in geo.children:
        child.destroy()

    # Create In/Out based on family
    if family == 'POP':
        in_op = geo.create(inPOP, 'in1')
        out_op = geo.create(outPOP, 'out1')
    else:  # SOP (default)
        in_op = geo.create(inSOP, 'in1')
        out_op = geo.create(outSOP, 'out1')

    in_op.viewer = True
    out_op.viewer = True
    out_op.inputConnectors[0].connect(in_op)
    out_op.display = True
    out_op.render = True

    # Connect external input
    if input_op is not None:
        geo.inputConnectors[0].connect(input_op)

    return geo, in_op, out_op


def ChainOperators(self, operators: list[OP]) -> list[OP]:
    """Connect operators in sequence with auto layout.

    Connects operators using inputConnectors (same family only).
    Each operator is positioned `LAYOUT_X_SPACING` (250px) to the right of
    the previous one, matching the gmss layout convention.

    Args:
        operators: List of operators to chain [first, second, third, ...]

    Returns:
        list[OP]: The same list of operators (for chaining)

    Example:
        chain = ChainOperators([grid, noise, null])
        bounds = GetBounds(chain)  # Get bounds of entire chain

    Note:
        For cross-family connections (SOP -> CHOP etc.), use par.sop/par.chop
        directly as conversion operators don't use inputConnectors.
    """
    if not operators:
        return []

    for i in range(1, len(operators)):
        prev_op = operators[i - 1]
        curr_op = operators[i]
        curr_op.inputConnectors[0].connect(prev_op)
        MoveOp(self, curr_op, prev_op.nodeX + LAYOUT_X_SPACING, prev_op.nodeY)

    return operators


_help_data_cache: dict[str, str | dict] | None = None


def _get_help_data() -> dict[str, str | dict]:
    """Load TD's built-in help data (internal helper, cached)."""
    global _help_data_cache
    if _help_data_cache is None:
        import json
        _help_data_cache = json.loads(op('/ui/dialogs/parGrabber/offlineHelp').text)
    assert _help_data_cache is not None
    return _help_data_cache


def _get_family_key(op_type: str) -> str | None:
    """Get help family key from operator type (internal helper)."""
    family_map = {
        'SOP': 'SOPs', 'POP': 'POPs', 'TOP': 'TOPs',
        'CHOP': 'CHOPs', 'DAT': 'DATs', 'COMP': 'COMPs', 'MAT': 'MATs'
    }
    for suffix, family_key in family_map.items():
        if op_type.endswith(suffix):
            return family_key
    return None


def GetOperatorInfo(self, op_type: str) -> dict[str, Any] | None:
    """Get operator info from TD's built-in help.

    Args:
        op_type: Operator type name (e.g., 'spherePOP', 'glslTOP')

    Returns:
        dict: {'summary': str, 'label': str, 'parameters': dict} or None
    """
    help_data = _get_help_data()
    family_key = _get_family_key(op_type)
    if family_key:
        return help_data['help'].get(family_key, {}).get(op_type)
    return None


def GetParameterList(self, op_type: str) -> list[str]:
    """Get list of parameter names for an operator type.

    Args:
        op_type: Operator type name (e.g., 'spherePOP', 'glslTOP')

    Returns:
        list: Parameter names, or empty list if not found
    """
    info = GetOperatorInfo(self, op_type)
    if info and 'parameters' in info:
        return list(info['parameters'].keys())
    return []


def GetParameterHelp(self, op_type: str, param_name: str) -> dict[str, Any] | None:
    """Get help for a specific parameter.

    Args:
        op_type: Operator type name (e.g., 'spherePOP')
        param_name: Parameter name (e.g., 'type')

    Returns:
        dict: Parameter info or None
    """
    info = GetOperatorInfo(self, op_type)
    if info and 'parameters' in info:
        return info['parameters'].get(param_name)
    return None


def PrintLayout(self, base: OP | None = None) -> None:
    """Print layout of child operators.

    Args:
        base: Parent operator (defaults to ownerComp.parent())
    """
    if base is None:
        base = self.ownerComp.parent()

    for child in sorted(base.children, key=lambda c: (c.nodeY, c.nodeX)):
        print(f"{child.name}: ({child.nodeX}, {child.nodeY}) [{child.family}]")


def CheckErrors(self, target: OP | str, recurse: bool = True) -> str:
    """Check and print errors.

    Args:
        target: Operator or path string (required)
        recurse: Check children recursively

    Returns:
        str: Error string or empty

    Raises:
        ValueError: If target is None or invalid path
    """
    if target is None:
        raise ValueError("target is required and cannot be None")

    if isinstance(target, str):
        resolved = op(target)
        if resolved is None:
            raise ValueError(f"Invalid operator path: {target}")
        target = resolved

    # Force cook to detect errors
    target.cook(force=True)

    errors = target.errors(recurse=recurse)
    if errors:
        print(f"Errors in {target.path}: {errors}")
    return errors


# =============================================================================
# Layout Utilities
# =============================================================================

def GetBounds(self, target: OP | str | list[OP | str]) -> AABB:
    """Get bounding box including docked operators.

    Args:
        target: Operator, path string, or list of operators

    Returns:
        AABB: Bounding box with min_x, min_y, max_x, max_y
              Also has .width, .height, .x, .y properties
    """
    # Handle list of operators
    if isinstance(target, list):
        if not target:
            return AABB(0, 0, 0, 0)
        all_bounds = [GetBounds(self, op) for op in target]
        return AABB(
            min(b.min_x for b in all_bounds),
            min(b.min_y for b in all_bounds),
            max(b.max_x for b in all_bounds),
            max(b.max_y for b in all_bounds),
        )

    # Handle single operator
    if isinstance(target, str):
        target = op(target)

    min_x = target.nodeX
    min_y = target.nodeY
    max_x = target.nodeX + target.nodeWidth
    max_y = target.nodeY + target.nodeHeight

    for d in target.docked:
        min_x = min(min_x, d.nodeX)
        min_y = min(min_y, d.nodeY)
        max_x = max(max_x, d.nodeX + d.nodeWidth)
        max_y = max(max_y, d.nodeY + d.nodeHeight)

    return AABB(min_x, min_y, max_x, max_y)


def _aabb_overlap(b1: AABB, b2: AABB) -> bool:
    """AABB overlap check for two bounds (internal helper)."""
    return not (b1.max_x <= b2.min_x or  # b1 is left of b2
                b2.max_x <= b1.min_x or  # b2 is left of b1
                b1.max_y <= b2.min_y or  # b1 is below b2 (Y up)
                b2.max_y <= b1.min_y)    # b2 is below b1


def CheckOverlap(
    self,
    bounds1: AABB | list[AABB],
    bounds2: AABB | list[AABB],
) -> bool:
    """Check if any bounds in bounds1 overlap with any bounds in bounds2.

    Args:
        bounds1: Single AABB or list of AABBs
        bounds2: Single AABB or list of AABBs

    Returns:
        True if any overlap exists
    """
    # Normalize to list
    list1 = [bounds1] if isinstance(bounds1, AABB) else list(bounds1)
    list2 = [bounds2] if isinstance(bounds2, AABB) else list(bounds2)

    for b1 in list1:
        for b2 in list2:
            if _aabb_overlap(b1, b2):
                return True
    return False


def GetAllBounds(self, base: OP | str) -> list[AABB]:
    """Get bounds of all children in container.

    Args:
        base: Container operator or path string

    Returns:
        List of AABB for each child operator
    """
    if isinstance(base, str):
        base = op(base)
    return [GetBounds(self, child) for child in base.children]


def FindEmptyArea(
    self,
    base: OP | str,
    width: int,
    height: int,
    start_x: int = 0,
    start_y: int = 0,
    margin: int = 50,
) -> tuple[int, int]:
    """Find empty area for placing an operator.

    Algorithm:
    1. Generate candidate positions (start + adjacent to existing ops)
    2. Sort candidates (prefer closer to start_x, then Y closer to start_y)
    3. Return first non-overlapping candidate
    4. Fallback: rightmost + margin

    Args:
        base: Container operator or path string
        width: Required width (including docked)
        height: Required height (including docked)
        start_x: Preferred start X position
        start_y: Preferred start Y position
        margin: Space between operators

    Returns:
        (x, y) position for placement
    """
    if isinstance(base, str):
        base = op(base)

    all_bounds = GetAllBounds(self, base)

    if not all_bounds:
        return (start_x, start_y)

    # Generate candidates
    candidates = [(start_x, start_y)]

    for b in all_bounds:
        # Right of existing (same Y)
        candidates.append((b.max_x + margin, b.min_y))
        # Above existing (same X)
        candidates.append((b.min_x, b.max_y + margin))
        # Below existing (same X)
        candidates.append((b.min_x, b.min_y - height - margin))

    # Sort: prefer closer to start_x, then Y closer to start_y
    candidates.sort(key=lambda c: (abs(c[0] - start_x), abs(c[1] - start_y)))

    # Find first non-overlapping
    for (x, y) in candidates:
        candidate_bounds = AABB(x, y, x + width, y + height)
        if not CheckOverlap(self, candidate_bounds, all_bounds):
            return (x, y)

    # Fallback: rightmost + margin
    rightmost = max(b.max_x for b in all_bounds)
    return (rightmost + margin, start_y)


def FindTypeConversionPosition(
    self,
    source_op: OP | str,
    target_width: int,
    target_height: int,
    direction: str = 'auto',
    margin: int = 40,
) -> tuple[int, int]:
    """Find position for type conversion operator.

    Places the new operator at the same X as source, shifted in Y direction.

    Args:
        source_op: Source operator or path string
        target_width: Width of new operator (including docked)
        target_height: Height of new operator (including docked)
        direction: 'up', 'down', or 'auto' (check both, prefer less collision)
        margin: Space between operators

    Returns:
        (x, y) position for placement
    """
    if isinstance(source_op, str):
        source_op = op(source_op)

    source_bounds = GetBounds(self, source_op)
    base = source_op.parent()
    all_bounds = GetAllBounds(self, base)

    # Remove source from collision check
    all_bounds = [b for b in all_bounds if b != source_bounds]

    source_x = source_bounds.min_x

    # Calculate candidate positions
    pos_above = (source_x, source_bounds.max_y + margin)
    pos_below = (source_x, source_bounds.min_y - target_height - margin)

    if direction == 'up':
        candidates = [pos_above, pos_below]
    elif direction == 'down':
        candidates = [pos_below, pos_above]
    else:  # auto
        # Check which has less collision potential
        bounds_above = AABB(pos_above[0], pos_above[1],
                            pos_above[0] + target_width, pos_above[1] + target_height)
        bounds_below = AABB(pos_below[0], pos_below[1],
                            pos_below[0] + target_width, pos_below[1] + target_height)

        overlap_above = CheckOverlap(self, bounds_above, all_bounds) if all_bounds else False
        overlap_below = CheckOverlap(self, bounds_below, all_bounds) if all_bounds else False

        if not overlap_above:
            return pos_above
        elif not overlap_below:
            return pos_below
        else:
            # Both overlap, try shifting X
            candidates = [pos_above, pos_below]

    # Try candidates, shift X if needed
    for (x, y) in candidates:
        for x_offset in range(0, 1000, 200):  # Try shifting right
            test_bounds = AABB(x + x_offset, y,
                               x + x_offset + target_width, y + target_height)
            if not all_bounds or not CheckOverlap(self, test_bounds, all_bounds):
                return (x + x_offset, y)

    # Fallback
    return pos_above


# =============================================================================
# Layout-rule helpers (gmss convention)
#
# These helpers enforce the project's node-layout convention so networks stay
# scannable as they grow. See skills/td-guide/reference/layout-rules.md.
#
# Core idea:
#   - Wired chain (feeding geo.in1)        -> SAME Y row as geo COMP.
#   - Reference chain (referenced by name) -> BELOW geo, last node directly
#                                             under geo (same X column).
# =============================================================================

def AlignReferenceUnderGeo(self, ref_chain, geo) -> list:
    """Align a reference chain so its END node sits directly under the geo COMP.

    The rule: the last node of a reference chain (the one consumed via a
    parameter reference such as instanceop, instancerottoop, material, etc.)
    is placed at (geo.nodeX, geo.nodeY - LAYOUT_Y_FAMILY). Earlier nodes in
    the chain extend LEFT from there with LAYOUT_X_SPACING between them.

    Args:
        ref_chain: list of operators ordered as the data flow:
            [source, ..., end_null]. end_null is the one referenced by geo.
        geo: the geometry COMP this chain is referenced by (op or path string)

    Returns:
        list: the same chain (chainable)
    """
    if not ref_chain:
        return []
    if isinstance(geo, str):
        geo = op(geo)

    end_x = geo.nodeX
    end_y = geo.nodeY - LAYOUT_Y_FAMILY

    # Walk from the END of the chain back toward the SOURCE, placing each node
    # LAYOUT_X_SPACING to the left of the next.
    n = len(ref_chain)
    for i, node in enumerate(reversed(ref_chain)):
        x = end_x - (i * LAYOUT_X_SPACING)
        MoveOp(self, node, x, end_y)

    return ref_chain


def AlignInstanceChainWithGeo(self, instance_chain, geo) -> list:
    """Align a wired instance-shape chain on the same row as its geo COMP.

    The rule: the chain that feeds geo.in1 via a wire sits at the same Y as
    the geo (with LAYOUT_GEO_Y_OFFSET adjustment for COMP visual height).
    The LAST node ends one LAYOUT_X_SPACING step to the left of geo, so the
    wire from chain-end into geo.in1 is short and clear.

    Args:
        instance_chain: list of operators ordered as the data flow:
            [shape, ..., null_into_geo].
        geo: the geometry COMP receiving the chain via wire (op or path)

    Returns:
        list: the same chain
    """
    if not instance_chain:
        return []
    if isinstance(geo, str):
        geo = op(geo)

    end_x = geo.nodeX - LAYOUT_X_SPACING
    end_y = geo.nodeY + LAYOUT_GEO_Y_OFFSET

    for i, node in enumerate(reversed(instance_chain)):
        x = end_x - (i * LAYOUT_X_SPACING)
        MoveOp(self, node, x, end_y)

    return instance_chain


def LayoutGeoGroup(
    self,
    geo,
    instance_chain: list | None = None,
    reference_chain: list | None = None,
    geo_x: int | None = None,
    geo_y: int | None = None,
):
    """Lay out a Geometry COMP and its associated chains in one call.

    Applies the project convention:
      - Optionally move the geo COMP to (geo_x, geo_y).
      - Place the instance (wired) chain on the same Y row as the geo,
        ending one step left of geo.
      - Place the reference chain below the geo, ending directly under it.

    Args:
        geo: Geometry COMP (op or path string).
        instance_chain: optional list [shape, ..., null_into_geo] feeding geo.in1.
        reference_chain: optional list [source, ..., end_null] referenced by
            geo via a parameter (instanceop, instancerottoop, etc.).
        geo_x: optional new X for the geo (keeps current if None).
        geo_y: optional new Y for the geo (keeps current if None).

    Returns:
        OP: the geo (chainable).

    Example:
        # body group
        op.TDAPI.LayoutGeoGroup(
            geo1,
            instance_chain=[lens1, null_box],
            reference_chain=[sphere1, noise1, noise_curl, null_src],
            geo_x=1050, geo_y=-70,
        )
    """
    if isinstance(geo, str):
        geo = op(geo)

    if geo_x is not None or geo_y is not None:
        MoveOp(
            self, geo,
            geo_x if geo_x is not None else geo.nodeX,
            geo_y if geo_y is not None else geo.nodeY,
        )

    if instance_chain:
        AlignInstanceChainWithGeo(self, instance_chain, geo)

    if reference_chain:
        AlignReferenceUnderGeo(self, reference_chain, geo)

    return geo


def VerifyNoOverlaps(
    self,
    base,
    ignore_owner_docked: bool = True,
) -> list:
    """Check that no operators in `base` overlap visually.

    Returns the list of overlapping (name_a, name_b) pairs. Empty list = clean.

    Docked DATs (e.g. glslMAT's _vertex/_pixel/_info) are physically inside
    their owner's bounding box and would always register as overlaps. With
    ignore_owner_docked=True (default), such pairs are filtered out.

    Args:
        base: container operator or path string.
        ignore_owner_docked: skip (owner, docked) pseudo-overlaps.

    Returns:
        list of (name_a, name_b) tuples for any real overlaps.
    """
    if isinstance(base, str):
        base = op(base)

    children = list(base.children)
    bounds_list = [GetBounds(self, c) for c in children]

    overlaps = []
    for i in range(len(children)):
        for j in range(i + 1, len(children)):
            ci, cj = children[i], children[j]
            if ignore_owner_docked:
                if ci in cj.docked or cj in ci.docked:
                    continue
            if _aabb_overlap(bounds_list[i], bounds_list[j]):
                overlaps.append((ci.name, cj.name))
    return overlaps
