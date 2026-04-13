const express = require('express');
const router = express.Router();

/**
 * Get all users.
 * @see UserService
 * @returns {User[]} list of users
 */
router.get('/users', async (req, res) => {
  res.json([]);
});

/**
 * Get user by ID.
 * @param {string} id - user id
 * @returns {User} the user
 */
router.get('/users/:id', async (req, res) => {
  res.json({ id: req.params.id });
});

/** Create a new user. */
router.post('/users', async (req, res) => {
  res.status(201).json(req.body);
});

/** Update a user. */
router.put('/users/:id', async (req, res) => {
  res.json(req.body);
});

/** Delete a user. */
router.delete('/users/:id', async (req, res) => {
  res.json({ deleted: req.params.id });
});

module.exports = router;
