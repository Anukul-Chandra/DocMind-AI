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
  { title: "Documents", href: "/app/documents", icon: FileText },
  { title: "Chat", href: "/app/chat", icon: MessagesSquare },
];

export const pageTitles: Record<string, string> = {
  "/app": "Dashboard",
  "/app/documents": "Documents",
  "/app/chat": "Chat",
};
