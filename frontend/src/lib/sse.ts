/** Evento Server-Sent Events ya decodificado. */
export interface SSEEvent {
  event: string
  data: string
}

/**
 * Parser incremental de SSE. `EventSource` solo admite GET, y /ask/stream es POST,
 * así que el stream se lee con fetch y se decodifica a mano.
 *
 * `push` recibe trozos arbitrarios del cuerpo (pueden cortar un evento a la mitad)
 * y devuelve los eventos completos encontrados hasta ese momento.
 */
export class SSEParser {
  private buffer = ''

  push(chunk: string): SSEEvent[] {
    this.buffer += chunk.replace(/\r\n?/g, '\n')
    const events: SSEEvent[] = []
    let sep = this.buffer.indexOf('\n\n')
    while (sep !== -1) {
      const block = this.buffer.slice(0, sep)
      this.buffer = this.buffer.slice(sep + 2)
      const parsed = parseBlock(block)
      if (parsed) events.push(parsed)
      sep = this.buffer.indexOf('\n\n')
    }
    return events
  }
}

function parseBlock(block: string): SSEEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) continue // comentario / keep-alive
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
  }
  return data.length ? { event, data: data.join('\n') } : null
}
