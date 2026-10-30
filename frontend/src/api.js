// Every call to our backend lives in this one file.
// The browser only ever talks to OUR API — never to football-data.org directly —
// so the football-data.org key stays secret on the server (the "backend proxy" pattern).
import axios from "axios";

// Locally this is http://127.0.0.1:8000. In production, set VITE_API_URL in the
// Netlify/Vercel dashboard to your Render URL (e.g. https://ucl-predictor-api.onrender.com).
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://127.0.0.1:8000",
  timeout: 60000, // free Render servers can take ~50s to wake up
});

export const getHealth = () => api.get("/health").then((res) => res.data);
export const getTeams = () => api.get("/teams").then((res) => res.data);
export const getModelInfo = () => api.get("/model").then((res) => res.data);
export const getFixturePredictions = () =>
  api.get("/predict/fixtures").then((res) => res.data);
export const predictMatch = (homeId, awayId, neutral) =>
  api
    .get("/predict", { params: { home_id: homeId, away_id: awayId, neutral } })
    .then((res) => res.data);

// Turn an axios error into a sentence a human can read.
export function errorMessage(err) {
  if (err.response) return err.response.data?.detail || `Server error (${err.response.status})`;
  if (err.request) return "Couldn't reach the API. Is the backend running?";
  return err.message;
}
