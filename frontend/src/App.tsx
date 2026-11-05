import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import Discover from "./pages/Discover";
import Recommendations from "./pages/Recommendations";
import Profile from "./pages/Profile";
import Evaluation from "./pages/Evaluation";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Discover />} />
        <Route path="recommendations" element={<Recommendations />} />
        <Route path="profile" element={<Profile />} />
        <Route path="evaluation" element={<Evaluation />} />
        <Route path="*" element={<p className="py-10 text-center text-muted">Page not found.</p>} />
      </Route>
    </Routes>
  );
}
