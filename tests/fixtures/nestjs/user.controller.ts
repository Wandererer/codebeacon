import { Controller, Get, Post, Put, Delete, Body, Param } from '@nestjs/common';
import { Injectable } from '@nestjs/common';

@Injectable()
export class UserService {
  findAll() { return []; }
  findOne(id: number) { return { id }; }
  create(dto: any) { return dto; }
  update(id: number, dto: any) { return dto; }
  remove(id: number) { return { deleted: id }; }
}

@Controller('users')
export class UserController {
  constructor(private readonly userService: UserService) {}

  @Get()
  findAll() {
    return this.userService.findAll();
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.userService.findOne(+id);
  }

  @Post()
  create(@Body() createUserDto: any) {
    return this.userService.create(createUserDto);
  }

  @Put(':id')
  update(@Param('id') id: string, @Body() updateUserDto: any) {
    return this.userService.update(+id, updateUserDto);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.userService.remove(+id);
  }
}
