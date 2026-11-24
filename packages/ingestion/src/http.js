export async function getJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText} from ${url}: ${body.slice(0, 300)}`);
  }
  return response.json();
}
