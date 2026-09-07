export default function ErrorBanner({ children }) {
  if (!children) return null;
  return (
    <div className="error-banner" role="alert">
      {children}
    </div>
  );
}
