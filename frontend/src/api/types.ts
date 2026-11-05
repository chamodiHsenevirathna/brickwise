// Mirror of the API contract in docs/CONTRACTS.md. Keep the two in sync.
export interface Product {
  set_num: string;
  name: string;
  year: number | null;
  theme: string;
  root_theme: string;
  num_parts: number | null;
  image_url: string; // "/images/<file>"
}
export interface Feedback { id: number; set_num: string; rating: 0 | 1; created_at: string }
export interface FeedbackWithProduct extends Feedback { product: Product }
export interface NextProductsResponse { items: Product[]; remaining: number; total: number }
export interface FeedbackCreated { feedback: Feedback; remaining: number }
export interface FeedbackUndone { undone: Feedback; remaining: number }
export interface FeedbackList { items: FeedbackWithProduct[]; likes: number; passes: number }
export interface ModelStatus {
  ready: boolean; likes: number; passes: number; min_likes: number; min_passes: number;
  reason: string | null; backend: "faiss" | "numpy";
}
export interface ThemeStat { theme: string; likes: number; passes: number; like_rate: number }
export interface PreferenceSummary {
  likes: number; passes: number; total_rated: number; remaining: number;
  top_themes: ThemeStat[]; avg_parts_liked: number | null; avg_parts_passed: number | null;
  model: ModelStatus | { ready: false; reason: string };
}
export type Method = "logreg" | "similarity";
export interface SimilarLiked { product: Product; similarity: number }
export interface Recommendation { product: Product; score: number; explanation: string; similar_to: SimilarLiked[] }
export interface RecommendationsResponse {
  status: "ok" | "insufficient_feedback" | "unavailable"; method: Method; message: string;
  min_likes: number; min_passes: number; likes: number; passes: number; items: Recommendation[];
}
export interface MethodScore { precision_at_k: number; std: number }
export interface EvaluationReport {
  simulated: boolean; k: number; sufficient: boolean; reason: string | null;
  n_ratings: number; n_likes: number; n_passes: number; n_splits: number; protocol: string;
  methods: Partial<Record<"logreg" | "similarity" | "random", MethodScore>>;
  winner: string | null; base_rate: number;
}
