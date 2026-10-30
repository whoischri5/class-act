import { useEffect, useState } from "react";
import { Spinner } from "react-bootstrap";

// A spinner that, after a few seconds, explains why it's slow
// (free Render servers go to sleep and take a while to wake up).
export default function Loading({ label = "Loading…" }) {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), 5000);
    return () => clearTimeout(timer); // cleanup if we finish loading first
  }, []);

  return (
    <div className="text-center text-muted py-5">
      <Spinner animation="border" size="sm" className="me-2" />
      {label}
      {slow && <div className="small mt-2">The server may be waking up — this can take up to a minute.</div>}
    </div>
  );
}
