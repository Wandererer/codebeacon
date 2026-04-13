using Microsoft.AspNetCore.Mvc;

namespace Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public class UserController : ControllerBase
{
    private readonly IUserService _userService;

    public UserController(IUserService userService)
    {
        _userService = userService;
    }

    [HttpGet]
    public IActionResult GetAll()
    {
        return Ok(_userService.GetAll());
    }

    [HttpGet("{id}")]
    public IActionResult Get(int id)
    {
        return Ok(_userService.GetById(id));
    }

    [HttpPost]
    public IActionResult Create([FromBody] UserDto dto)
    {
        return Created($"/api/users/{dto.Id}", _userService.Create(dto));
    }

    [HttpPut("{id}")]
    public IActionResult Update(int id, [FromBody] UserDto dto)
    {
        return Ok(_userService.Update(id, dto));
    }

    [HttpDelete("{id}")]
    public IActionResult Delete(int id)
    {
        _userService.Delete(id);
        return NoContent();
    }
}
