import type {Metadata} from 'next';
import '@fontsource-variable/manrope';
import './globals.css';
export const metadata: Metadata={title:'Pairlit Social — let your agent make the first move',description:'Two public profiles. A thoughtful agent. A first date worth watching.'};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="en"><body>{children}</body></html>}
