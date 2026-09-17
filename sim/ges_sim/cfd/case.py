"""OpenFOAM case generatsiya (v2406 dictionary formatlari).

Case papkasi: 0/, constant/, system/, Allrun. Hisob og'irligini `resolution` (0.5–2) boshqaradi.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

NU = 1.14e-6
RHO = 998.2
G = 9.81

HEADER = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    object      {obj};
}}
"""


def _dict(cls: str, obj: str, body: str) -> str:
    return HEADER.format(cls=cls, obj=obj) + body.strip() + "\n"


@dataclass
class PenstockCase:
    """Bosimli quvur: o'q-simmetrik wedge, simpleFoam, k-epsilon. Uzunlik x o'qi bo'ylab."""

    length_m: float = 20.0
    diameter_m: float = 2.4
    flow_m3s: float = 20.0
    roughness_mm: float = 0.1
    resolution: float = 1.0  # 1 — o'rtacha (~6–10 ming yacheyka), 2 — mayda
    max_iterations: int = 400

    kind: str = field(default="penstock", init=False)

    @property
    def inlet_velocity(self) -> float:
        return self.flow_m3s / (math.pi * self.diameter_m**2 / 4)

    def summary_inputs(self) -> dict:
        return {
            "length_m": self.length_m,
            "diameter_m": self.diameter_m,
            "flow_m3s": self.flow_m3s,
            "inlet_velocity": round(self.inlet_velocity, 3),
        }

    def write(self, case: Path) -> None:
        L, R, U = self.length_m, self.diameter_m / 2, self.inlet_velocity
        nx = max(int(40 * self.resolution * max(L / (2 * R), 1) ** 0.5), 30)
        nr = max(int(20 * self.resolution), 12)
        a = math.radians(2.5)
        c, s = R * math.cos(a), R * math.sin(a)
        _w(
            case / "system/blockMeshDict",
            _dict(
                "dictionary",
                "blockMeshDict",
                f"""
scale 1;
vertices
(
    (0 0 0)          // 0 o'q
    ({L} 0 0)        // 1 o'q
    ({L} {c} {-s})   // 2
    (0 {c} {-s})     // 3
    ({L} {c} {s})    // 4
    (0 {c} {s})      // 5
);
blocks
(
    hex (0 1 2 3 0 1 4 5) ({nx} {nr} 1) simpleGrading (1 0.4 1)
);
edges ();
boundary
(
    inlet  {{ type patch; faces ((0 3 5 0)); }}
    outlet {{ type patch; faces ((1 4 2 1)); }}
    wall   {{ type wall;  faces ((3 2 4 5)); }}
    front  {{ type wedge; faces ((0 1 4 5)); }}
    back   {{ type wedge; faces ((0 3 2 1)); }}
    axis   {{ type empty; faces ((0 1 1 0)); }}
);
mergePatchPairs ();
""",
            ),
        )
        _write_common_incompressible(case, self.max_iterations)
        # Turbulent boshlang'ich: I=5 %, l=0.07 D
        k = 1.5 * (0.05 * U) ** 2
        eps = 0.09**0.75 * k**1.5 / (0.07 * 2 * R)
        bc_wedge = "front { type wedge; }\n    back { type wedge; }\n    axis { type empty; }"
        _w(
            case / "0/U",
            _dict(
                "volVectorField",
                "U",
                f"""
dimensions [0 1 -1 0 0 0 0];
internalField uniform ({U} 0 0);
boundaryField
{{
    inlet  {{ type fixedValue; value uniform ({U} 0 0); }}
    outlet {{ type zeroGradient; }}
    wall   {{ type noSlip; }}
    {bc_wedge}
}}
""",
            ),
        )
        _w(
            case / "0/p",
            _dict(
                "volScalarField",
                "p",
                f"""
dimensions [0 2 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{{
    inlet  {{ type zeroGradient; }}
    outlet {{ type fixedValue; value uniform 0; }}
    wall   {{ type zeroGradient; }}
    {bc_wedge}
}}
""",
            ),
        )
        _w(
            case / "0/k",
            _dict(
                "volScalarField",
                "k",
                f"""
dimensions [0 2 -2 0 0 0 0];
internalField uniform {k:.6g};
boundaryField
{{
    inlet  {{ type fixedValue; value uniform {k:.6g}; }}
    outlet {{ type zeroGradient; }}
    wall   {{ type kqRWallFunction; value uniform {k:.6g}; }}
    {bc_wedge}
}}
""",
            ),
        )
        _w(
            case / "0/epsilon",
            _dict(
                "volScalarField",
                "epsilon",
                f"""
dimensions [0 2 -3 0 0 0 0];
internalField uniform {eps:.6g};
boundaryField
{{
    inlet  {{ type fixedValue; value uniform {eps:.6g}; }}
    outlet {{ type zeroGradient; }}
    wall   {{ type epsilonWallFunction; value uniform {eps:.6g}; }}
    {bc_wedge}
}}
""",
            ),
        )
        ks = self.roughness_mm / 1000
        wall_nut = (
            f"{{ type nutkRoughWallFunction; Ks uniform {ks:.6g}; Cs uniform 0.5; value uniform 0; }}"
            if ks > 0
            else "{ type nutkWallFunction; value uniform 0; }"
        )
        _w(
            case / "0/nut",
            _dict(
                "volScalarField",
                "nut",
                f"""
dimensions [0 2 -1 0 0 0 0];
internalField uniform 0;
boundaryField
{{
    inlet  {{ type calculated; value uniform 0; }}
    outlet {{ type calculated; value uniform 0; }}
    wall   {wall_nut}
    {bc_wedge}
}}
""",
            ),
        )
        _w(
            case / "system/sample",
            _dict(
                "dictionary",
                "sample",
                f"""
type sets;
libs (sampling);
interpolationScheme cellPoint;
setFormat raw;
sets
(
    axis   {{ type uniform; axis x; start (0.01 {0.3 * R:.4f} 0); end ({L - 0.01} {0.3 * R:.4f} 0); nPoints 100; }}
    radial {{ type uniform; axis y; start ({0.9 * L:.4f} 0 0); end ({0.9 * L:.4f} {R * 0.999:.4f} 0); nPoints 30; }}
);
fields (p U);
""",
            ),
        )
        _w(
            case / "system/plane",
            _dict(
                "dictionary",
                "plane",
                """
type surfaces;
libs (sampling);
surfaceFormat raw;
interpolationScheme cellPoint;
surfaces
(
    plane { type cuttingPlane; planeType pointAndNormal; pointAndNormalDict { point (0 0 0); normal (0 0 1); } interpolate true; }
);
fields (p U);
""",
            ),
        )
        _w(
            case / "Allrun",
            """#!/bin/sh
cd "${0%/*}" || exit 1
. ${WM_PROJECT_DIR:?}/bin/tools/RunFunctions
runApplication blockMesh
runApplication simpleFoam
runApplication postProcess -func sample -latestTime
runApplication -s plane postProcess -func plane -latestTime
touch DONE
""",
            executable=True,
        )


@dataclass
class SpillwayCase:
    """Keng ostonali suv tashlagich ustidan oqim: 2D, interFoam (VOF), laminar."""

    crest_height_m: float = 3.0  # ostona balandligi (kanal tubidan)
    head_m: float = 1.0  # ostona ustidagi napor (boshlang'ich suv sathi)
    crest_length_m: float = 4.0  # oqim bo'ylab ostona uzunligi
    upstream_m: float = 10.0
    downstream_m: float = 12.0
    unit_discharge_m2s: float | None = (
        None  # q, m³/s bir metr kenglikka (None — napordan hisoblanadi)
    )
    resolution: float = 1.0
    end_time_s: float = 15.0

    kind: str = field(default="spillway", init=False)

    @property
    def q(self) -> float:
        if self.unit_discharge_m2s is not None:
            return self.unit_discharge_m2s
        # keng ostona: q = 1.7 · H^1.5  (m=0.385)
        return 1.7 * self.head_m**1.5

    def summary_inputs(self) -> dict:
        return {
            "crest_height_m": self.crest_height_m,
            "head_m": self.head_m,
            "crest_length_m": self.crest_length_m,
            "unit_discharge_m2s": round(self.q, 4),
        }

    def write(self, case: Path) -> None:
        hc, ht = self.crest_height_m, self.crest_height_m + max(self.head_m, 0.5) * 2.5
        x1, x2, x3 = (
            self.upstream_m,
            self.upstream_m + self.crest_length_m,
            self.upstream_m + self.crest_length_m + self.downstream_m,
        )
        d = 0.15 / self.resolution  # yacheyka o'lchami, m
        n = lambda length: max(int(length / d), 4)  # noqa: E731
        y0 = hc + self.head_m
        _w(
            case / "system/blockMeshDict",
            _dict(
                "dictionary",
                "blockMeshDict",
                f"""
scale 1;
vertices
(
    (0 0 0) ({x1} 0 0) ({x2} 0 0) ({x3} 0 0)          // 0-3 tub
    (0 {hc} 0) ({x1} {hc} 0) ({x2} {hc} 0) ({x3} {hc} 0)  // 4-7 ostona sathi
    (0 {ht} 0) ({x1} {ht} 0) ({x2} {ht} 0) ({x3} {ht} 0)  // 8-11 yuqori
    (0 0 1) ({x1} 0 1) ({x2} 0 1) ({x3} 0 1)
    (0 {hc} 1) ({x1} {hc} 1) ({x2} {hc} 1) ({x3} {hc} 1)
    (0 {ht} 1) ({x1} {ht} 1) ({x2} {ht} 1) ({x3} {ht} 1)
);
blocks
(
    hex (0 1 5 4 12 13 17 16) ({n(x1)} {n(hc)} 1) simpleGrading (1 1 1)          // yuqori oqim, past
    hex (4 5 9 8 16 17 21 20) ({n(x1)} {n(ht - hc)} 1) simpleGrading (1 1 1)     // yuqori oqim, ust
    hex (5 6 10 9 17 18 22 21) ({n(x2 - x1)} {n(ht - hc)} 1) simpleGrading (1 1 1) // ostona usti
    hex (2 3 7 6 14 15 19 18) ({n(x3 - x2)} {n(hc)} 1) simpleGrading (1 1 1)     // quyi oqim, past
    hex (6 7 11 10 18 19 23 22) ({n(x3 - x2)} {n(ht - hc)} 1) simpleGrading (1 1 1) // quyi oqim, ust
);
edges ();
boundary
(
    inlet      {{ type patch; faces ((0 12 16 4) (4 16 20 8)); }}
    outlet     {{ type patch; faces ((3 7 19 15) (7 11 23 19)); }}
    atmosphere {{ type patch; faces ((8 20 21 9) (9 21 22 10) (10 22 23 11)); }}
    bottom     {{ type wall;  faces ((0 1 13 12) (2 3 15 14)); }}
    weir       {{ type wall;  faces ((1 5 17 13) (5 6 18 17) (6 2 14 18)); }}
    frontAndBack {{ type empty; faces ((0 4 5 1) (4 8 9 5) (5 9 10 6) (2 6 7 3) (6 10 11 7) (12 13 17 16) (16 17 21 20) (17 18 22 21) (14 15 19 18) (18 19 23 22)); }}
);
mergePatchPairs ();
""",
            ),
        )
        _w(
            case / "system/controlDict",
            _dict(
                "dictionary",
                "controlDict",
                f"""
application     interFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {self.end_time_s};
deltaT          0.001;
writeControl    adjustable;
writeInterval   {self.end_time_s};
purgeWrite      2;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable yes;
adjustTimeStep  yes;
maxCo           0.6;
maxAlphaCo      0.6;
maxDeltaT       0.05;
functions
{{
    outletFlow
    {{
        type            surfaceFieldValue;
        libs            (fieldFunctionObjects);
        regionType      patch;
        name            outlet;
        operation       sum;
        fields          (alphaPhi0.water);
        writeControl    timeStep;
        writeInterval   50;
        log             false;
        writeFields     false;
    }}
}}
""",
            ),
        )
        _w(
            case / "system/fvSchemes",
            _dict(
                "dictionary",
                "fvSchemes",
                """
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes
{
    div(rhoPhi,U)  Gauss linearUpwind grad(U);
    div(phi,alpha) Gauss vanLeer;
    div(phirb,alpha) Gauss linear;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
""",
            ),
        )
        _w(
            case / "system/fvSolution",
            _dict(
                "dictionary",
                "fvSolution",
                """
solvers
{
    "alpha.water.*" { nAlphaCorr 2; nAlphaSubCycles 1; cAlpha 1; MULESCorr yes; nLimiterIter 5; solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0; }
    "pcorr.*" { solver PCG; preconditioner DIC; tolerance 1e-6; relTol 0; }
    p_rgh { solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0.05; }
    p_rghFinal { $p_rgh; relTol 0; }
    "(U|k|epsilon)" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-6; relTol 0; }
    "(U|k|epsilon)Final" { $U; relTol 0; }
}
PIMPLE { momentumPredictor no; nOuterCorrectors 1; nCorrectors 3; nNonOrthogonalCorrectors 0; }
relaxationFactors { equations { ".*" 1; } }
""",
            ),
        )
        _w(
            case / "constant/g",
            _dict(
                "uniformDimensionedVectorField",
                "g",
                "dimensions [0 1 -2 0 0 0 0];\nvalue (0 -9.81 0);",
            ),
        )
        _w(
            case / "constant/transportProperties",
            _dict(
                "dictionary",
                "transportProperties",
                f"""
phases (water air);
water {{ transportModel Newtonian; nu {NU}; rho {RHO}; }}
air   {{ transportModel Newtonian; nu 1.48e-05; rho 1; }}
sigma 0.07;
""",
            ),
        )
        _w(
            case / "constant/turbulenceProperties",
            _dict("dictionary", "turbulenceProperties", "simulationType laminar;"),
        )
        _w(
            case / "0/alpha.water.orig",
            _dict(
                "volScalarField",
                "alpha.water",
                """
dimensions [0 0 0 0 0 0 0];
internalField uniform 0;
boundaryField
{
    inlet      { type variableHeightFlowRate; lowerBound 0; upperBound 1; value uniform 0; }
    outlet     { type inletOutlet; inletValue uniform 0; value uniform 0; }
    atmosphere { type inletOutlet; inletValue uniform 0; value uniform 0; }
    bottom     { type zeroGradient; }
    weir       { type zeroGradient; }
    frontAndBack { type empty; }
}
""",
            ),
        )
        _w(
            case / "0/U",
            _dict(
                "volVectorField",
                "U",
                f"""
dimensions [0 1 -1 0 0 0 0];
internalField uniform (0 0 0);
boundaryField
{{
    inlet      {{ type variableHeightFlowRateInletVelocity; alpha alpha.water; flowRate constant {self.q:.6g}; value uniform (0 0 0); }}
    outlet     {{ type inletOutlet; inletValue uniform (0 0 0); value uniform (0 0 0); }}
    atmosphere {{ type pressureInletOutletVelocity; value uniform (0 0 0); }}
    bottom     {{ type noSlip; }}
    weir       {{ type noSlip; }}
    frontAndBack {{ type empty; }}
}}
""",
            ),
        )
        _w(
            case / "0/p_rgh",
            _dict(
                "volScalarField",
                "p_rgh",
                """
dimensions [1 -1 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{
    inlet      { type fixedFluxPressure; value uniform 0; }
    outlet     { type zeroGradient; }
    atmosphere { type totalPressure; p0 uniform 0; }
    bottom     { type fixedFluxPressure; value uniform 0; }
    weir       { type fixedFluxPressure; value uniform 0; }
    frontAndBack { type empty; }
}
""",
            ),
        )
        _w(
            case / "system/setFieldsDict",
            _dict(
                "dictionary",
                "setFieldsDict",
                f"""
defaultFieldValues ( volScalarFieldValue alpha.water 0 );
regions
(
    boxToCell {{ box (-1 -1 -1) ({x2 + 0.5} {y0} 2); fieldValues ( volScalarFieldValue alpha.water 1 ); }}
    boxToCell {{ box ({x2 + 0.5} -1 -1) ({x3 + 1} {0.15} 2); fieldValues ( volScalarFieldValue alpha.water 1 ); }}
);
""",
            ),
        )
        _w(
            case / "system/surface",
            _dict(
                "dictionary",
                "surface",
                """
type surfaces;
libs (sampling);
surfaceFormat raw;
interpolationScheme cellPoint;
surfaces
(
    water { type isoSurfaceCell; isoField alpha.water; isoValue 0.5; interpolate true; }
    plane { type cuttingPlane; planeType pointAndNormal; pointAndNormalDict { point (0 0 0.5); normal (0 0 1); } interpolate true; }
);
fields (alpha.water U p_rgh);
""",
            ),
        )
        _w(
            case / "Allrun",
            """#!/bin/sh
cd "${0%/*}" || exit 1
. ${WM_PROJECT_DIR:?}/bin/tools/RunFunctions
cp 0/alpha.water.orig 0/alpha.water
runApplication blockMesh
runApplication setFields
runApplication interFoam
runApplication postProcess -func surface -latestTime
touch DONE
""",
            executable=True,
        )


@dataclass
class GeometryCase:
    """Model geometriyasi (IFC elementlari STL) atrofida oqim: 3D, snappyHexMesh + simpleFoam,
    k-epsilon. Suv +x yo'nalishda oqadi (inlet → outlet); element(lar) — devor (noSlip).
    Masalan suv qabul qilgich/ustun/to'g'on tanasi atrofida tezlik va bosim, gidrodinamik kuch.

    STL fayl case/constant/triSurface/body.stl da bo'lishi kerak (server yozadi); bbox — metrda."""

    bbox: list = field(default_factory=lambda: [[0, 0, 0], [1, 1, 1]])  # [[x0,y0,z0],[x1,y1,z1]]
    velocity_ms: float = 2.0  # kiruvchi oqim tezligi
    flow_axis: str = "x"  # oqim yo'nalishi: x | y
    resolution: float = 1.0  # fon yacheyka zichligi
    refinement: int = 2  # sirt atrofida qo'shimcha darajalar (1–3)
    max_iterations: int = 300
    submerged: bool = True  # to'liq suv ostida (erkin sirt yo'q)

    kind: str = field(default="geometry", init=False)

    @property
    def size(self) -> list[float]:
        lo, hi = self.bbox
        return [max(float(hi[i] - lo[i]), 1e-3) for i in range(3)]

    def domain(self) -> tuple[list[float], list[float]]:
        """Hisob sohasi: oqim bo'ylab oldinda 2L, orqada 5L, yon/tepa/pastda 2L (L — jism o'lchami)."""
        lo, hi = self.bbox
        L = max(self.size)
        ax = 0 if self.flow_axis == "x" else 1
        dlo = [float(lo[i]) - 2 * L for i in range(3)]
        dhi = [float(hi[i]) + 2 * L for i in range(3)]
        dhi[ax] = float(hi[ax]) + 5 * L
        # tub — jismning pastidan 0.5 L (daryo tubi kabi), tepa erkin sirt o'rnida slip
        dlo[2] = float(lo[2]) - 0.5 * L
        return dlo, dhi

    def summary_inputs(self) -> dict:
        return {
            "velocity_ms": self.velocity_ms,
            "flow_axis": self.flow_axis,
            "body_size_m": [round(v, 3) for v in self.size],
            "refinement": self.refinement,
        }

    def write(self, case: Path) -> None:
        dlo, dhi = self.domain()
        L = max(self.size)
        d = L / (12 * self.resolution)  # fon yacheyka, m
        n = [max(int((dhi[i] - dlo[i]) / d), 6) for i in range(3)]
        ax = 0 if self.flow_axis == "x" else 1
        U = [0.0, 0.0, 0.0]
        U[ax] = self.velocity_ms
        Ustr = f"({U[0]} {U[1]} {U[2]})"
        # blockMesh: inlet/outlet oqim o'qi bo'yicha
        faces = {
            "xmin": "(0 4 7 3)",
            "xmax": "(1 2 6 5)",
            "ymin": "(0 1 5 4)",
            "ymax": "(3 7 6 2)",
            "zmin": "(0 3 2 1)",
            "zmax": "(4 5 6 7)",
        }
        inlet, outlet = ("xmin", "xmax") if ax == 0 else ("ymin", "ymax")
        sides = [k for k in faces if k not in (inlet, outlet)]
        _w(
            case / "system/blockMeshDict",
            _dict(
                "dictionary",
                "blockMeshDict",
                f"""
scale 1;
vertices
(
    ({dlo[0]} {dlo[1]} {dlo[2]}) ({dhi[0]} {dlo[1]} {dlo[2]}) ({dhi[0]} {dhi[1]} {dlo[2]}) ({dlo[0]} {dhi[1]} {dlo[2]})
    ({dlo[0]} {dlo[1]} {dhi[2]}) ({dhi[0]} {dlo[1]} {dhi[2]}) ({dhi[0]} {dhi[1]} {dhi[2]}) ({dlo[0]} {dhi[1]} {dhi[2]})
);
blocks ( hex (0 1 2 3 4 5 6 7) ({n[0]} {n[1]} {n[2]}) simpleGrading (1 1 1) );
edges ();
boundary
(
    inlet  {{ type patch; faces ({faces[inlet]}); }}
    outlet {{ type patch; faces ({faces[outlet]}); }}
    sides  {{ type patch; faces ({" ".join(faces[k] for k in sides)}); }}
);
mergePatchPairs ();
""",
            ),
        )
        lo, hi = self.bbox
        pad = 0.5 * L
        # locationInMesh — soha ichida, jismdan tashqarida (inlet tomonda, tepada)
        loc = [
            dlo[0] + 0.3 * (dhi[0] - dlo[0]),
            dlo[1] + 0.5 * (dhi[1] - dlo[1]),
            dhi[2] - 0.2 * (dhi[2] - dlo[2]),
        ]
        if ax == 0:
            loc[0] = dlo[0] + 0.15 * (float(lo[0]) - dlo[0])
        else:
            loc[1] = dlo[1] + 0.15 * (float(lo[1]) - dlo[1])
        r = max(1, min(int(self.refinement), 3))
        _w(
            case / "system/snappyHexMeshDict",
            _dict(
                "dictionary",
                "snappyHexMeshDict",
                f"""
castellatedMesh true;
snap            true;
addLayers       false;
geometry
{{
    body.stl {{ type triSurfaceMesh; name body; }}
    refbox {{ type searchableBox; min ({float(lo[0]) - pad} {float(lo[1]) - pad} {float(lo[2]) - pad}); max ({float(hi[0]) + pad * 2} {float(hi[1]) + pad} {float(hi[2]) + pad}); }}
}}
castellatedMeshControls
{{
    maxLocalCells 2000000;
    maxGlobalCells 4000000;
    minRefinementCells 10;
    maxLoadUnbalance 0.1;
    nCellsBetweenLevels 2;
    features ();
    refinementSurfaces {{ body {{ level ({r} {r + 1}); patchInfo {{ type wall; }} }} }}
    resolveFeatureAngle 30;
    refinementRegions {{ refbox {{ mode inside; levels ((1e15 {max(r - 1, 1)})); }} }}
    locationInMesh ({loc[0]} {loc[1]} {loc[2]});
    allowFreeStandingZoneFaces true;
}}
snapControls
{{
    nSmoothPatch 3; tolerance 2.0; nSolveIter 30; nRelaxIter 5;
    nFeatureSnapIter 10; implicitFeatureSnap true; explicitFeatureSnap false; multiRegionFeatureSnap false;
}}
addLayersControls
{{
    relativeSizes true; layers {{ }} expansionRatio 1.0; finalLayerThickness 0.3; minThickness 0.1;
    nGrow 0; featureAngle 60; nRelaxIter 3; nSmoothSurfaceNormals 1; nSmoothNormals 3; nSmoothThickness 10;
    maxFaceThicknessRatio 0.5; maxThicknessToMedialRatio 0.3; minMedialAxisAngle 90; nBufferCellsNoExtrude 0; nLayerIter 50;
}}
meshQualityControls
{{
    maxNonOrtho 65; maxBoundarySkewness 20; maxInternalSkewness 4; maxConcave 80; minVol 1e-13; minTetQuality 1e-15;
    minArea -1; minTwist 0.02; minDeterminant 0.001; minFaceWeight 0.02; minVolRatio 0.01; minTriangleTwist -1;
    nSmoothScale 4; errorReduction 0.75;
}}
mergeTolerance 1e-6;
""",
            ),
        )
        _write_common_incompressible(case, self.max_iterations)
        # forces (gidrodinamik kuch, N — rho bilan) controlDict ga qo'shiladi
        cd = case / "system/controlDict"
        cd.write_text(
            cd.read_text(encoding="utf-8")
            + f"""
functions
{{
    forces
    {{
        type forces; libs (forces); patches (body); rho rhoInf; rhoInf {RHO};
        CofR ({(float(lo[0]) + float(hi[0])) / 2} {(float(lo[1]) + float(hi[1])) / 2} {(float(lo[2]) + float(hi[2])) / 2});
        writeControl timeStep; writeInterval {self.max_iterations};
    }}
}}
""",
            encoding="utf-8",
            newline="\n",
        )
        k = 1.5 * (0.05 * self.velocity_ms) ** 2
        eps = 0.09**0.75 * k**1.5 / (0.07 * L)
        _w(
            case / "0/U",
            _dict(
                "volVectorField",
                "U",
                f"""
dimensions [0 1 -1 0 0 0 0];
internalField uniform {Ustr};
boundaryField
{{
    inlet  {{ type fixedValue; value uniform {Ustr}; }}
    outlet {{ type zeroGradient; }}
    sides  {{ type slip; }}
    body   {{ type noSlip; }}
}}
""",
            ),
        )
        _w(
            case / "0/p",
            _dict(
                "volScalarField",
                "p",
                """
dimensions [0 2 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{
    inlet  { type zeroGradient; }
    outlet { type fixedValue; value uniform 0; }
    sides  { type zeroGradient; }
    body   { type zeroGradient; }
}
""",
            ),
        )
        for name, val, wall in (
            ("k", k, "kqRWallFunction"),
            ("epsilon", eps, "epsilonWallFunction"),
        ):
            _w(
                case / f"0/{name}",
                _dict(
                    "volScalarField",
                    name,
                    f"""
dimensions [0 2 {-2 if name == "k" else -3} 0 0 0 0];
internalField uniform {val:.6g};
boundaryField
{{
    inlet  {{ type fixedValue; value uniform {val:.6g}; }}
    outlet {{ type zeroGradient; }}
    sides  {{ type slip; }}
    body   {{ type {wall}; value uniform {val:.6g}; }}
}}
""",
                ),
            )
        _w(
            case / "0/nut",
            _dict(
                "volScalarField",
                "nut",
                """
dimensions [0 2 -1 0 0 0 0];
internalField uniform 0;
boundaryField
{
    inlet  { type calculated; value uniform 0; }
    outlet { type calculated; value uniform 0; }
    sides  { type calculated; value uniform 0; }
    body   { type nutkWallFunction; value uniform 0; }
}
""",
            ),
        )
        cz = (float(lo[2]) + float(hi[2])) / 2
        cy = (float(lo[1]) + float(hi[1])) / 2 if ax == 0 else (float(lo[0]) + float(hi[0])) / 2
        vnormal = "(0 1 0)" if ax == 0 else "(1 0 0)"
        vpoint = f"(0 {cy} 0)" if ax == 0 else f"({cy} 0 0)"
        _w(
            case / "system/plane",
            _dict(
                "dictionary",
                "plane",
                f"""
type surfaces;
libs (sampling);
surfaceFormat raw;
interpolationScheme cellPoint;
surfaces
(
    plane  {{ type cuttingPlane; planeType pointAndNormal; pointAndNormalDict {{ point (0 0 {cz}); normal (0 0 1); }} interpolate true; }}
    vplane {{ type cuttingPlane; planeType pointAndNormal; pointAndNormalDict {{ point {vpoint}; normal {vnormal}; }} interpolate true; }}
    body   {{ type patch; patches (body); interpolate false; }}
);
fields (p U);
""",
            ),
        )
        _w(
            case / "Allrun",
            """#!/bin/sh
cd "${0%/*}" || exit 1
. ${WM_PROJECT_DIR:?}/bin/tools/RunFunctions
runApplication blockMesh
runApplication snappyHexMesh -overwrite
runApplication simpleFoam
runApplication -s plane postProcess -func plane -latestTime
touch DONE
""",
            executable=True,
        )


def _write_common_incompressible(case: Path, iterations: int) -> None:
    _w(
        case / "system/controlDict",
        _dict(
            "dictionary",
            "controlDict",
            f"""
application     simpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {iterations};
deltaT          1;
writeControl    timeStep;
writeInterval   {iterations};
purgeWrite      1;
writeFormat     ascii;
writePrecision  6;
timeFormat      general;
timePrecision   6;
runTimeModifiable yes;
""",
        ),
    )
    _w(
        case / "system/fvSchemes",
        _dict(
            "dictionary",
            "fvSchemes",
            """
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes
{
    default none;
    div(phi,U) bounded Gauss linearUpwind grad(U);
    div(phi,k) bounded Gauss limitedLinear 1;
    div(phi,epsilon) bounded Gauss limitedLinear 1;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
wallDist { method meshWave; }
""",
        ),
    )
    _w(
        case / "system/fvSolution",
        _dict(
            "dictionary",
            "fvSolution",
            """
solvers
{
    p { solver GAMG; smoother GaussSeidel; tolerance 1e-7; relTol 0.01; }
    "(U|k|epsilon)" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-7; relTol 0.1; }
}
SIMPLE
{
    nNonOrthogonalCorrectors 0;
    consistent yes;
    residualControl { p 1e-4; U 1e-5; "(k|epsilon)" 1e-5; }
}
relaxationFactors { equations { U 0.9; ".*" 0.9; } }
""",
        ),
    )
    _w(
        case / "constant/transportProperties",
        _dict("dictionary", "transportProperties", f"transportModel Newtonian;\nnu {NU};"),
    )
    _w(
        case / "constant/turbulenceProperties",
        _dict(
            "dictionary",
            "turbulenceProperties",
            "simulationType RAS;\nRAS { RASModel kEpsilon; turbulence on; printCoeffs on; }",
        ),
    )


def _w(path: Path, text: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    if executable:
        path.chmod(0o755)


def build_case(params: dict, case_dir: Path):
    """JSON parametrlardan case obyekti yaratib, papkaga yozadi. Qaytaradi: case obyekti."""
    kind = params.get("kind", "penstock")
    cls = {"penstock": PenstockCase, "spillway": SpillwayCase, "geometry": GeometryCase}.get(kind)
    if cls is None:
        raise ValueError(f"Noma'lum CFD turi: {kind} (penstock|spillway|geometry)")
    fields = {k: v for k, v in params.items() if k in cls.__dataclass_fields__ and k != "kind"}
    case = cls(**fields)
    _validate(case)
    case.write(case_dir)
    return case


def _validate(case) -> None:
    if isinstance(case, PenstockCase):
        if case.length_m <= 0 or case.diameter_m <= 0 or case.flow_m3s <= 0:
            raise ValueError("Quvur: uzunlik, diametr, sarf musbat bo'lishi kerak")
        if not 0.3 <= case.resolution <= 3:
            raise ValueError("resolution 0.3–3 oralig'ida")
    elif isinstance(case, GeometryCase):
        lo, hi = case.bbox
        if len(lo) != 3 or len(hi) != 3 or any(float(hi[i]) <= float(lo[i]) for i in range(3)):
            raise ValueError("Geometriya: bbox noto'g'ri (element tanlanmagan?)")
        if case.velocity_ms <= 0 or case.flow_axis not in ("x", "y"):
            raise ValueError("Geometriya: tezlik musbat, oqim o'qi x yoki y")
        if not 0.3 <= case.resolution <= 3:
            raise ValueError("resolution 0.3–3 oralig'ida")
    else:
        if case.crest_height_m <= 0 or case.head_m <= 0 or case.crest_length_m <= 0:
            raise ValueError("Suv tashlagich: balandlik, napor, uzunlik musbat bo'lishi kerak")
        if not 0.3 <= case.resolution <= 3:
            raise ValueError("resolution 0.3–3 oralig'ida")
