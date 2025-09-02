/**
 * Graph visualization (TypeScript)
 */

let graphInstance: any;

export function showGraph(data: any) {
  // ForceGraph might be a global factory function provided by a bundled lib
  const nodeWidth = 160;
  const container = document.getElementById("schema-graph") as HTMLDivElement;
  graphInstance = (ForceGraph as any)()(container)
    .graphData(data)
    .nodeId("name")
    .width(container.clientWidth)
    .height(container.clientHeight)
    .nodeCanvasObject((node: any, ctx: CanvasRenderingContext2D) => {
      const lineHeight = 14;
      const padding = 8;
      const headerHeight = 20;
      const fontSize = 12;
      const textColor = "#111";
      const fillColor = "#f6f6f6";
      const strokeColor = "#222";

      if (!node.height) {
        node.height =
          headerHeight + (node.columns?.length || 0) * lineHeight + padding * 2;
      }

      ctx.fillStyle = fillColor;
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1;
      ctx.fillRect(
        node.x - nodeWidth / 2,
        node.y - node.height / 2,
        nodeWidth,
        node.height
      );
      ctx.strokeRect(
        node.x - nodeWidth / 2,
        node.y - node.height / 2,
        nodeWidth,
        node.height
      );

      ctx.fillStyle = textColor;
      ctx.font = `bold ${fontSize}px Arial`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(
        node.name,
        node.x,
        node.y - node.height / 2 + headerHeight / 2 + padding / 2
      );

      ctx.font = `${fontSize - 2}px Arial`;
      ctx.textAlign = "left";
      const startX = node.x - nodeWidth / 2 + padding;
      let colY = node.y - node.height / 2 + headerHeight + padding;
      (node.columns || []).forEach((col: any) => {
        let name = col;
        let type = null;
        if (typeof col === "object") {
          name = col.name || "";
          type = col.type || col.dataType || null;
        }

        ctx.textAlign = "left";
        ctx.fillStyle = "#000";
        ctx.fillText(name, startX, colY);

        if (type) {
          ctx.fillStyle = "#555";
          const nameWidth = ctx.measureText(name).width;
          const available = nodeWidth - padding * 2 - nameWidth - 8;
          let typeText = String(type);
          if (available > 0) {
            if (ctx.measureText(typeText).width > available) {
              while (
                typeText.length > 0 &&
                ctx.measureText(typeText + "…").width > available
              ) {
                typeText = typeText.slice(0, -1);
              }
              typeText = typeText + "…";
            }
            ctx.textAlign = "right";
            ctx.fillText(typeText, node.x + nodeWidth / 2 - padding, colY);
          }
          ctx.fillStyle = "#000";
          ctx.textAlign = "left";
        }

        colY += lineHeight;
      });
    })
    .linkCanvasObject((link: any, ctx: CanvasRenderingContext2D) => {
      const getEdgeColor = () => {
        try {
          const root = getComputedStyle(document.documentElement);
          const cssEdge = root.getPropertyValue("--edge-color");
          if (cssEdge && cssEdge.trim()) return cssEdge.trim();

          const bg = getComputedStyle(document.body).backgroundColor || "";
          const m = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
          if (m) {
            const r = parseInt(m[1], 10) / 255;
            const g = parseInt(m[2], 10) / 255;
            const b = parseInt(m[3], 10) / 255;
            const L = 0.2126 * r + 0.7152 * g + 0.0722 * b;
            return L > 0.6 ? "#111" : "#ffffff";
          }
        } catch {
          // ignore
        }
        return "#ffffff";
      };

      const edgeColor = getEdgeColor();
      ctx.strokeStyle = edgeColor;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(link.source.x, link.source.y);
      ctx.lineTo(link.target.x, link.target.y);
      ctx.stroke();
    })
    .nodePointerAreaPaint(
      (node: any, color: string, ctx: CanvasRenderingContext2D) => {
        ctx.fillStyle = color;
        const padding = 5;
        ctx.fillRect(
          node.x - nodeWidth / 2 - padding,
          node.y - node.height / 2 - padding,
          nodeWidth + padding * 2,
          node.height + padding * 2
        );
      }
    )

  if (
    typeof (window as any).d3 !== "undefined" &&
    typeof (window as any).d3.forceManyBody === "function"
  ) {
    const d3 = (window as any).d3;
    graphInstance.d3Force("charge", d3.forceManyBody().strength(-900));
    graphInstance.d3Force(
      "link",
      d3
        .forceLink()
        .id((d: any) => d.name)
        .distance(220)
        .strength(0.9)
    );

    if (typeof d3.forceCollide === "function") {
      graphInstance.d3Force(
        "collision",
        d3
          .forceCollide()
          .radius(() => 90)
          .strength(0.9)
      );
    }
  }

  try {
    const computedBg = getComputedStyle(document.body).backgroundColor || "";
    const pickColor = (bg: string) => {
      try {
        const m = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
        if (m) {
          const r = parseInt(m[1], 10) / 255;
          const g = parseInt(m[2], 10) / 255;
          const b = parseInt(m[3], 10) / 255;
          const L = 0.2126 * r + 0.7152 * g + 0.0722 * b;
          return L > 0.6 ? "#111" : "#ffffff";
        }
      } catch {
        /* empty */
      }
      return "#ffffff";
    };
    const edgeColor = (() => {
      const root = getComputedStyle(document.documentElement);
      const cssEdge = root.getPropertyValue("--edge-color");
      if (cssEdge && cssEdge.trim()) return cssEdge.trim();
      return pickColor(computedBg);
    })();

    graphInstance
      .linkColor(() => edgeColor)
      .linkDirectionalArrowLength(6)
      .linkDirectionalArrowRelPos(1);
  } catch {
    graphInstance.linkDirectionalArrowLength(6).linkDirectionalArrowRelPos(1);
  }

  const zoomInButton = document.getElementById("schema-controls-zoom-in") as HTMLButtonElement;
  const zoomOutButton = document.getElementById("schema-controls-zoom-out") as HTMLButtonElement;
  const centerButton = document.getElementById("schema-controls-center") as HTMLButtonElement;

  zoomInButton.addEventListener("click", () => {
    graphInstance.zoom(graphInstance.zoom() * 1.1);
  });
  zoomOutButton.addEventListener("click", () => {
    graphInstance.zoom(graphInstance.zoom() * 0.9);
  });
  centerButton.addEventListener("click", () => {
    center();
  });
}

const center = () => {
  const canvas = document.getElementById(
    "schema-graph"
  ) as HTMLCanvasElement;

  if (canvas) {
    const rect = canvas.getBoundingClientRect();
    const minDimension = Math.min(rect.width, rect.height);
    const padding = minDimension * 0.1;
    graphInstance.zoomToFit(500, padding);
  } 
}
export function resizeGraph() {
  if (graphInstance) {
    const container = document.getElementById("schema-graph") as HTMLDivElement;
    if (container) {
      graphInstance.width(container.clientWidth).height(container.clientHeight);
      center();
    }
  }
}
