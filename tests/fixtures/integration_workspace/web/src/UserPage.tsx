import { useState, useEffect } from "react";

export interface User {
  id: number;
  name: string;
}

export function UserPage({ userId }: { userId: number }) {
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    fetch(`/users/${userId}`).then((r) => r.json()).then(setUser);
  }, [userId]);
  return <div>{user?.name ?? "loading"}</div>;
}
