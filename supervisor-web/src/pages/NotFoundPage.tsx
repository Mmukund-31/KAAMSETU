import { Link } from "react-router-dom";
import { Card } from "../components/ui";

export function NotFoundPage() {
  return (
    <Card>
      <div className="py-10 text-center">
        <p className="text-sm font-medium text-ink">Page not found</p>
        <Link to="/" className="mt-3 inline-block text-sm font-medium text-primary-700 hover:underline">
          Go to the overview
        </Link>
      </div>
    </Card>
  );
}
