import {
  FileText,
  LayoutDashboard,
  MessagesSquare,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  title: string;
  href: string;
  icon: LucideIcon;
}

export const appNavItems: NavItem[] = [
  { title: "Dashboard", href: "/app", icon: LayoutDashboard },
  { title: "Library", href: "/app/documents", icon: FileText },
  { title: "Chat", href: "/app/chat", icon: MessagesSquare },
];

export const pageTitles: Record<string, string> = {
  "/app": "Dashboard",
  "/app/documents": "Library",
  "/app/chat": "Chat",
};
