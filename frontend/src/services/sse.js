// A text/event-stream body, split into events. Every event PolicyPal sends
// has one JSON data line (ADR 0027).
export function createSseParser(onEvent) {
  let buffer = "";

  function dispatch(block) {
    let event = "message";
    const data = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (data.length > 0) onEvent({ event, data: JSON.parse(data.join("\n")) });
  }

  return {
    push(text) {
      buffer += text.replaceAll("\r\n", "\n");
      let end;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        dispatch(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
      }
    },
    end() {
      if (buffer.trim()) dispatch(buffer);
      buffer = "";
    },
  };
}
