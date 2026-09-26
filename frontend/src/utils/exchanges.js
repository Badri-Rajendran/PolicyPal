// Messages as question-and-answer pairs: the transcript sets each question as
// its answer's heading.
export function toExchanges(messages) {
  const exchanges = [];
  for (const message of messages) {
    const open = exchanges.at(-1);
    if (message.role === "assistant" && open && open.answer === null && open.question) {
      open.answer = message;
    } else if (message.role === "assistant") {
      exchanges.push({ key: message.id, question: null, answer: message });
    } else {
      exchanges.push({ key: message.id, question: message, answer: null });
    }
  }
  return exchanges;
}
