import Link from "next/link";

interface NavLink {
  href: string;
  label: string;
}

const navLinks: NavLink[] = [
  { href: "/menu", label: "Menu" },
  { href: "/order", label: "Order" },
  { href: "/payment", label: "Payment" },
  { href: "/settings", label: "Settings" },
  { href: "/admin/menu", label: "Manage menu" },
];

export default function HomePage() {
  return (
    <main className="container">
      <h1 className="title">Brew and Bean</h1>
      <p className="description">
        Welcome to Brew and Bean — great coffee, made simple.
      </p>
      <nav>
        <ul className="nav-list">
          {navLinks.length > 0 ? (
            navLinks.map((link) => (
              <li key={link.href} className="nav-item">
                <Link href={link.href}>{link.label}</Link>
              </li>
            ))
          ) : (
            <li>No navigation links available</li>
          )}
        </ul>
      </nav>
    </main>
  );
}

// CSS styles (to be included in a separate CSS file)
.container {
  max-width: 640px;
  margin: 0 auto;
  padding: 2rem 1rem;
}
.title {
  font-size: 2rem;
  margin-bottom: 0.5rem;
}
.description {
  margin-bottom: 1.5rem;
  color: #555;
}
.nav-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.nav-item {
  /* Additional styles for nav items can be added here */
}
