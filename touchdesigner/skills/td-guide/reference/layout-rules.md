# Node Layout Rules (gmss convention)

Apply these layout rules to every TouchDesigner network you create or modify
via the MCP. Networks grow fast; without a convention they become unreadable.
This convention is enforced by helpers in `op.TDAPI` (see bottom of file).

The rules below were established by the project author (gamsasyo) on
2026-05-14 and apply to every subsequent session unless explicitly overridden.

---

## Core principles

1. **Data flow on X.** Operators flow strictly left to right. Never create
   backward connections or zigzag arrangements. If a downstream op needs
   upstream data, restructure rather than route around.

2. **Same chain / same family on one Y row.** A POP source chain occupies
   one horizontal row. An instance-shape chain occupies another. Don't
   stack within a single chain.

3. **Logical groups separated on Y.** Body group, spine group, env-prep
   group, etc., each get their own Y band. Use `LAYOUT_Y_GROUP` between
   distinct groups for visual breathing room.

4. **Wired chain (instance shape) = SAME Y as its GEO COMP.** The chain
   that feeds `geo.in1` via a wire sits at the same vertical level as the
   geo COMP itself. The COMP gets a small downward offset
   (`LAYOUT_GEO_Y_OFFSET`) to account for its taller visual size.

   ```
   lens (X-LAYOUT_X_SPACING*2, Y) ─ null_in (X-LAYOUT_X_SPACING, Y) ──wire──→ geo (X, Y+OFFSET)
   ```

5. **Reference chain = SEPARATE Y, BELOW the geo.** Chains that are not
   wired but referenced by parameter (`instanceop`, `instancerottoop`,
   `material`, `sampler*top`, `camera`, `lights`) live one row below the
   geo group.

   **★ The final null of a reference chain MUST sit directly under the
   geo COMP (same X column).** The chain extends LEFT from that anchor,
   so the visual reading is "the thing being referenced is right under
   the thing referencing it."

   ```
   source ─ middle ─ end_null    ← end_null.nodeX == geo.nodeX
                          ↑ (Y = geo.nodeY - LAYOUT_Y_FAMILY)
   ```

6. **Spacing constants.**
   - `LAYOUT_X_SPACING` = 250 px — between ops in the same chain
   - `LAYOUT_Y_FAMILY` = 175 px — between rows of the same group
   - `LAYOUT_Y_GROUP` = 300 px+ — between logical groups
   - `LAYOUT_GEO_Y_OFFSET` = 20 px — geo COMP vertical offset from instance row

7. **GEO column = single X column.** All `geometryCOMP`s line up in the
   same X column (e.g., X = 1050). Predictable scanning.

8. **MAT column = right of GEO column.** Materials sit immediately right
   of the geo column. **Watch the docked-DAT extent**: a `glslMAT` has
   `_vertex` / `_pixel` / `_info` DATs that visually extend ~450 px to
   the right of the MAT node. Leave that space before placing the render
   column, otherwise overlap.

9. **Render output column = far right.** `render → null → post-process
   → final null` runs horizontally along the rightmost edge.

10. **Camera + Light = above render TOP, same X column.** Stack `cam1`,
    `light1`, ambient/fill lights vertically above `render1` so they
    share the X position with their consumer.

11. **Env / texture prep chain = bottom row, separate group.** External
    texture pipelines (HDR → level → null → referenced by MAT sampler)
    live at the bottom of the network in their own Y band.

12. **Null intermediary before every reference.** Insert `null<family>`
    right before any op that will be referenced by name. Consumers
    always read from `null_x`, never directly from the source — making
    upstream swaps safe.

13. **Always use `op.TDAPI.MoveOp`, never raw `nodeX/nodeY`.** `MoveOp`
    handles docked DATs automatically. Setting `nodeX/Y` directly leaves
    docked DATs orphaned.

14. **★ NO OVERLAPS.** Every op must have its own bounding box. Verify
    after every layout pass with `op.TDAPI.VerifyNoOverlaps(base)`. The
    helper ignores (owner, docked-DAT) pseudo-overlaps automatically.

---

## Helpers (`op.TDAPI`)

These functions encode the rules above. Prefer them over manual `nodeX/Y`
math whenever you can.

### `LayoutGeoGroup(geo, instance_chain, reference_chain, geo_x, geo_y)`

One call lays out a geo COMP and both of its chains following the rules.

```python
# After creating ops and wiring them, lay them out:
op.TDAPI.LayoutGeoGroup(
    geo1,
    instance_chain=[lens1, null_box],
    reference_chain=[sphere1, noise1, noise_curl, null_src],
    geo_x=1050, geo_y=-70,
)
# Now:
#   lens1, null_box      sit at Y=-50 (same row as geo1, offset)
#   geo1                 at (1050, -70)
#   sphere1..null_src    sit at Y=-245, with null_src.nodeX = 1050
```

### `AlignReferenceUnderGeo(ref_chain, geo)`

Positions a reference chain so its END node is directly under the geo,
with earlier nodes extending left.

```python
op.TDAPI.AlignReferenceUnderGeo(
    [sphere1, noise1, noise_curl, null_src],
    geo1,
)
```

### `AlignInstanceChainWithGeo(instance_chain, geo)`

Positions a wired instance chain on the same Y row as the geo, ending
one X step left of the geo.

```python
op.TDAPI.AlignInstanceChainWithGeo([lens1, null_box], geo1)
```

### `VerifyNoOverlaps(base, ignore_owner_docked=True)`

Returns a list of overlapping `(name_a, name_b)` pairs in `base`. Empty
list = clean layout. Ignores docked DATs by default.

```python
overlaps = op.TDAPI.VerifyNoOverlaps('/project1')
assert not overlaps, f"Layout has overlaps: {overlaps}"
```

---

## Workflow

After any structural change to a network:

1. Call `LayoutGeoGroup` (or the individual aligners) on each geo group.
2. Place camera/light/render/output column explicitly to the right of MAT.
3. Run `VerifyNoOverlaps`. If any pair returned, shift the offender
   right or down using `FindEmptyArea`.
4. Run `PrintLayout` for a sanity check.

When the chain layout is correct, the network reads top-to-bottom like
a recipe: source chains feed into geo COMPs, MAT references the geos,
render TOP consumes them, post chain finishes the output.
