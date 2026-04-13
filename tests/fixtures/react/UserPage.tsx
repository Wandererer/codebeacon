import React, { useState, useEffect } from 'react';

interface User {
  id: number;
  name: string;
}

/**
 * User list page component.
 * @see UserCard
 * @param {Object} props - component props
 */
const UserPage: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);

  useEffect(() => {
    fetch('/api/users').then(r => r.json()).then(setUsers);
  }, []);

  return (
    <div>
      <h1>Users</h1>
      {users.map(u => <div key={u.id}>{u.name}</div>)}
    </div>
  );
};

export default UserPage;
