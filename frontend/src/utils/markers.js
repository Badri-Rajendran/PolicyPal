// The model cites as [Source: label; label] and names plans as [Plan: id]
// (src/services/generation.py). These become seals and plan links; nothing
// else in the text is interpreted, and nothing becomes raw HTML.
const MARKER = /\[(Source|Plan):\s*([^\]]+)\]/g;

// Link text can't hold a button, so markers inside a link stay text.
const SKIP = new Set(["link", "linkReference"]);

// A seal's number is its source's position in message.sources, which the API
// orders by relevance. A label cited twice keeps its first number.
export function sourceNumbers(sources = []) {
  const numbers = new Map();
  sources.forEach((s, i) => {
    if (!numbers.has(s.source)) numbers.set(s.source, i + 1);
  });
  return numbers;
}

function planIndex(plans = []) {
  return new Map(plans.map((p, i) => [p.hios_plan_id, { position: i + 1, name: p.name }]));
}

function sealNode(number, label) {
  return {
    type: "ppSeal",
    data: { hName: "pp-seal", hProperties: { number, label }, hChildren: [{ type: "text", value: String(number) }] },
  };
}

function planNode(plan, planId) {
  return {
    type: "ppPlan",
    data: {
      hName: "pp-plan",
      hProperties: { position: plan.position, planId },
      hChildren: [{ type: "text", value: plan.name }],
    },
  };
}

function splitText(value, numbers, planned) {
  const nodes = [];
  let last = 0;
  for (const match of value.matchAll(MARKER)) {
    const [whole, kind, body] = match;
    const replacement = [];
    if (kind === "Source") {
      for (const label of body.split(";").map((l) => l.trim()).filter(Boolean)) {
        const number = numbers.get(label);
        if (number) replacement.push(sealNode(number, label));
      }
    } else {
      const planId = body.trim();
      const plan = planned.get(planId);
      if (!plan) continue; // unknown plan: leave the text
      replacement.push(planNode(plan, planId));
    }
    if (match.index > last) nodes.push({ type: "text", value: value.slice(last, match.index) });
    nodes.push(...replacement);
    last = match.index + whole.length;
  }
  if (last < value.length) nodes.push({ type: "text", value: value.slice(last) });
  return nodes;
}

// A remark plugin: react-markdown calls it with the options and runs the
// transformer it returns. The custom elements are rendered by AnswerBody.
export function remarkMarkers({ sources, plans } = {}) {
  const numbers = sourceNumbers(sources);
  const planned = planIndex(plans);
  function walk(node) {
    if (!Array.isArray(node.children) || SKIP.has(node.type)) return;
    node.children = node.children.flatMap((child) => {
      if (child.type === "text") return splitText(child.value, numbers, planned);
      walk(child);
      return [child];
    });
  }
  return (tree) => walk(tree);
}

// The answer as plain text for the clipboard: seals as [n], plans by name.
export function copyText(content, sources, plans) {
  const numbers = sourceNumbers(sources);
  const planned = planIndex(plans);
  return content.replace(MARKER, (whole, kind, body) => {
    if (kind === "Plan") return planned.get(body.trim())?.name ?? whole;
    return body
      .split(";")
      .map((l) => numbers.get(l.trim()))
      .filter(Boolean)
      .map((n) => `[${n}]`)
      .join("");
  });
}
