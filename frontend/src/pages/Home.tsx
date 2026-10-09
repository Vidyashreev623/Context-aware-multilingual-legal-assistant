import { Link } from "react-router-dom";

export default function Home() {
  return (
    <div className="h-screen w-screen flex flex-col items-center justify-center bg-slate-50 text-center px-6">
      <h1 className="text-3xl font-bold text-indigo-700 mb-2">Context-Aware Multilingual Indian Legal Assistant</h1>
      <p className="text-slate-600 mb-6">Indian Law</p>
      <Link
        to="/chat"
        className="bg-indigo-600 text-white px-6 py-3 rounded-xl font-medium hover:bg-indigo-700"
      >
        Start a conversation
      </Link>
    </div>
  );
}
