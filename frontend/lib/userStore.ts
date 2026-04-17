// userStore — Redis-backed persistence in production with JSON fallback for local dev

import fs from "fs";
import path from "path";
import crypto from "crypto";
import { createClient } from "redis";

const DB_PATH = path.join(process.cwd(), "data", "users.json");
const USERS_KEY = "stocxi:auth:users";
const REDIS_URL = process.env.REDIS_URL;

export interface User {
  id: string;
  name: string;
  email: string;
  passwordHash: string | null; // null for Google-only accounts
  provider: "credentials" | "google";
  createdAt: string;
}

type AppRedisClient = ReturnType<typeof createClient>;

let redisClientPromise: Promise<AppRedisClient | null> | null = null;

async function getRedisClient(): Promise<AppRedisClient | null> {
  if (!REDIS_URL) return null;
  if (!redisClientPromise) {
    redisClientPromise = (async () => {
      try {
        const client = createClient({ url: REDIS_URL });
        client.on("error", () => {
          // Keep auth flow resilient; fallback storage handles transient issues.
        });
        await client.connect();
        return client;
      } catch {
        return null;
      }
    })();
  }
  return redisClientPromise;
}

function readUsersFromFile(): User[] {
  try {
    const raw = fs.readFileSync(DB_PATH, "utf-8");
    return JSON.parse(raw) as User[];
  } catch {
    return [];
  }
}

function writeUsersToFile(users: User[]): void {
  // ensure data dir exists
  const dir = path.dirname(DB_PATH);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(DB_PATH, JSON.stringify(users, null, 2), "utf-8");
}

async function readUsers(): Promise<User[]> {
  try {
    const client = await getRedisClient();
    if (!client) return readUsersFromFile();

    const raw = await client.get(USERS_KEY);
    if (!raw) return [];

    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as User[]) : [];
  } catch {
    return readUsersFromFile();
  }
}

async function writeUsers(users: User[]): Promise<boolean> {
  try {
    const client = await getRedisClient();
    if (!client) {
      writeUsersToFile(users);
      return true;
    }
    await client.set(USERS_KEY, JSON.stringify(users));
    return true;
  } catch {
    try {
      writeUsersToFile(users);
      return true;
    } catch {
      return false;
    }
  }
}

export async function findUserByEmail(email: string): Promise<User | undefined> {
  const users = await readUsers();
  return users.find((u) => u.email.toLowerCase() === email.toLowerCase());
}

export async function addUser(user: Omit<User, "id" | "createdAt">): Promise<User | null> {
  const users = await readUsers();
  const newUser: User = {
    ...user,
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
  };
  users.push(newUser);
  const ok = await writeUsers(users);
  if (!ok) return null;
  return newUser;
}

export async function upsertGoogleUser(name: string, email: string): Promise<User | null> {
  // if account exists (any provider), return it; else create
  const existing = await findUserByEmail(email);
  if (existing) return existing;
  return addUser({ name, email, passwordHash: null, provider: "google" });
}
