import './globals.css';

export const metadata = {
  title: 'Incident Dashboard',
  description: 'Live ops-center incident feed',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <div id="root">{children}</div>
      </body>
    </html>
  );
}
