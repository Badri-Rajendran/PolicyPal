// The API's 422 carries [{field, message}]; forms show them beside each field.
export function fieldErrorsFrom(error) {
  return Object.fromEntries((error?.details ?? []).map(({ field, message }) => [field, message]));
}
