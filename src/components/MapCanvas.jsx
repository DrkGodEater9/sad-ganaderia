import { useMemo, useRef } from "react";
import { boundingBox } from "../utils/geo.js";

const SIZE = 600;
const PAD = 30;
const PLOT = SIZE - PAD * 2;
const SNAP_PX = 12;

export default function MapCanvas({ boundary, potreros, current, onAddPoint, currentColor }) {
  const svgRef = useRef(null);

  const bbox = useMemo(
    () => boundingBox([boundary, ...potreros.map((p) => p.pointsXY), current]),
    [boundary, potreros, current]
  );

  const m2s = ([x, y]) => [
    PAD + ((x - bbox.xmin) / (bbox.xmax - bbox.xmin)) * PLOT,
    PAD + ((bbox.ymax - y) / (bbox.ymax - bbox.ymin)) * PLOT,
  ];
  const s2m = ([sx, sy]) => [
    bbox.xmin + ((sx - PAD) / PLOT) * (bbox.xmax - bbox.xmin),
    bbox.ymax - ((sy - PAD) / PLOT) * (bbox.ymax - bbox.ymin),
  ];
  const pathOf = (pts) => pts.map((p) => m2s(p).join(",")).join(" ");

  function handleClick(evt) {
    const svg = svgRef.current;
    const pt = svg.createSVGPoint();
    const t = evt.touches && evt.touches.length ? evt.touches[0] : evt;
    pt.x = t.clientX;
    pt.y = t.clientY;
    const loc = pt.matrixTransform(svg.getScreenCTM().inverse());

    if (current.length >= 3) {
      const first = m2s(current[0]);
      const d = Math.hypot(first[0] - loc.x, first[1] - loc.y);
      if (d < SNAP_PX) {
        onAddPoint(null); // señal especial: cerrar
        return;
      }
    }
    onAddPoint(s2m([loc.x, loc.y]));
  }

  return (
    <div className="svgwrap">
      <svg ref={svgRef} viewBox={`0 0 ${SIZE} ${SIZE}`} onClick={handleClick}>
        <rect x="0" y="0" width={SIZE} height={SIZE} fill="#eef2ea" />

        {boundary.length > 2 && (
          <polygon points={pathOf(boundary)} fill="#dfe7d8" stroke="#9aa892" strokeWidth="1.5" />
        )}

        {potreros.map((p, i) => {
          const c = p.pointsXY.reduce(
            (acc, pt) => [acc[0] + pt[0] / p.pointsXY.length, acc[1] + pt[1] / p.pointsXY.length],
            [0, 0]
          );
          const sc = m2s(c);
          return (
            <g key={i}>
              <polygon
                points={pathOf(p.pointsXY)}
                fill={p.color + "33"}
                stroke={p.color}
                strokeWidth="2"
              />
              <text x={sc[0]} y={sc[1]} fontSize="11" fill={p.color} textAnchor="middle" fontWeight="600">
                {p.name}
              </text>
            </g>
          );
        })}

        {current.length > 0 && (
          <>
            {current.length > 1 && (
              <polyline
                points={pathOf(current)}
                fill="none"
                stroke={currentColor}
                strokeWidth="2"
                strokeDasharray="5,4"
              />
            )}
            {current.map((pt, i) => {
              const s = m2s(pt);
              return (
                <circle
                  key={i}
                  cx={s[0]}
                  cy={s[1]}
                  r={i === 0 ? 6 : 4}
                  fill={currentColor}
                  stroke="#fff"
                  strokeWidth="1.5"
                />
              );
            })}
          </>
        )}
      </svg>
    </div>
  );
}
