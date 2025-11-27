import { useEffect, useState } from 'react';

// Returns true if the viewport is less than the given breakpoint (default: 768px)
export function useIsMobile(breakpoint = 768): boolean {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(`(max-width: ${breakpoint - 1}px)`).matches : false
  );

  useEffect(() => {
    const media = window.matchMedia(`(max-width: ${breakpoint - 1}px)`);
    const listener = () => setIsMobile(media.matches);
    media.addEventListener('change', listener);
    setIsMobile(media.matches);
    return () => media.removeEventListener('change', listener);
  }, [breakpoint]);

  return isMobile;
}
