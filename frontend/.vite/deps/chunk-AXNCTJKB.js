import {
  getConfig2
} from "./chunk-AS236WFQ.js";
import {
  select_default
} from "./chunk-LKHU2X6C.js";
import {
  __name
} from "./chunk-UEB47VSI.js";

// node_modules/mermaid/dist/chunks/mermaid.core/chunk-CLGD4ZFX.mjs
var selectSvgElement = __name((id) => {
  const { securityLevel } = getConfig2();
  let root = select_default("body");
  if (securityLevel === "sandbox") {
    const sandboxElement = select_default(`#i${id}`);
    const doc = sandboxElement.node()?.contentDocument ?? document;
    root = select_default(doc.body);
  }
  const svg = root.select(`#${id}`);
  return svg;
}, "selectSvgElement");

export {
  selectSvgElement
};
//# sourceMappingURL=chunk-AXNCTJKB.js.map
