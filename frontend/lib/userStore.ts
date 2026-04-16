// userStore — JSON file-based user persistence for email/password auth

import fs from "fs";
import path from "path";
import crypto from "crypto";

const DB_PATH = path.join(process.cwd(), "data", "users.json");

export interface User {
  id: string;
  name: string;
  email: string;
  passwordHash: string | null; // null for Google-only accounts
  provider: "credentials" | "google";
  createdAt: string;
}

function readUsers(): User[] {
  try {
    const raw = fs.readFileSync(DB_PATH, "utf-8");
    return JSON.parse(raw) as User[];
  } catch {
    return [];
  }
}

function writeUsers(users: User[]): void {
  // ensure data dir exists
  const dir = path.dirname(DB_PATH);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(DB_PATH, JSON.stringify(users, null, 2), "utf-8");
}

export function findUserByEmail(email: string): User | undefined {
  return readUsers().find((u) => u.email.toLowerCase() === email.toLowerCase());
}

export function addUser(user: Omit<User, "id" | "createdAt">): User {
  const users = readUsers();
  const newUser: User = {
    ...user,
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
  };
  users.push(newUser);
  writeUsers(users);
  return newUser;
}

export function upsertGoogleUser(name: string, email: string): User {
  // if account exists (any provider), return it; else create
  const existing = findUserByEmail(email);
  if (existing) return existing;
  return addUser({ name, email, passwordHash: null, provider: "google" });
}
