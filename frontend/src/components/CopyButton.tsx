import { useEffect, useRef, useState } from 'react'
import { copyText } from '../utils/certificateUi'

type Props = {
  value: string
  label?: string
  className?: string
  title?: string
}

function CopyButton({
  value,
  label = 'Copy',
  className = 'copy-button',
  title,
}: Props) {
  const [status, setStatus] = useState<'idle' | 'copied' | 'error'>('idle')
  const timer = useRef<number | null>(null)

  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
  }, [])

  async function handleCopy() {
    try {
      await copyText(value)
      setStatus('copied')
    } catch {
      setStatus('error')
    }
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setStatus('idle'), 2200)
  }

  return (
    <button
      className={className}
      onClick={() => void handleCopy()}
      type="button"
      title={title ?? `Copy ${value}`}
      aria-live="polite"
    >
      {status === 'copied' ? 'Copied' : status === 'error' ? 'Copy failed' : label}
    </button>
  )
}

export default CopyButton
